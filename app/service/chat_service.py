import threading
from decouple import config
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from app.tools.math_tool import get_math_tool, get_dataframe_schema
from app.tools.search_tool import get_search_tool

# Google retires Gemini model versions periodically; override with the GEMINI_MODEL
# env var (e.g. on Render) to switch models without a code change.
GEMINI_MODEL = config("GEMINI_MODEL", default="gemini-3.8-flash")

BASE_SYSTEM_PROMPT = (
    "You are an expert data analytics assistant capable of complex data analysis and statistical reasoning. "
    "You have access to a spreadsheet dataset represented in memory as a pandas DataFrame named `df`.\n\n"
    "Available tools:\n"
    "1. `execute_pandas_code`: Executes Python expressions on `df` for calculations, math, counts, sums, averages, unique values, grouping, and filtering.\n"
    "2. `semantic_search`: Searches text content using semantic similarity.\n\n"
    "Instructions:\n"
    "- For questions about dataset schema (column names, row count, sample data), answer directly using the schema provided below without calling tools.\n"
    "- For math, averages, counts, unique categories/values (e.g. payment methods, customer types), calculations, or aggregations, call `execute_pandas_code` with a clean Python expression operating on `df` (e.g. `df['Method of Payment'].unique()`).\n"
    "- Only call `semantic_search` if searching for fuzzy/unstructured text across row content.\n"
    "- Always provide clear, accurate, and concise answers based on the calculation results."
)


class ChatService:
    """
    Constructed once per project and cached at the application level
    (see app.core.service_cache).

    The single LangGraph ReAct agent is compiled ONCE in __init__ and reused for
    every subsequent request. Per-request DB session safety is achieved via
    threading.local(): ask_question() sets self._local.db before invoking
    the agent, and the semantic_search tool reads self._local.db at call
    time rather than closing over a specific session object.
    """

    def __init__(self, project_id: int, file_path: str):
        self.project_id = project_id
        self.file_path = file_path

        # Thread-local storage for the per-request DB session.
        self._local = threading.local()

        def _get_db():
            # LangGraph runs tools in a worker thread where self._local.db was never
            # set, so return None and let the tool open its own session.
            return getattr(self._local, "db", None)

        # LLM client — reused across all requests for this project
        self.llm = ChatGoogleGenerativeAI(model=GEMINI_MODEL, temperature=0)

        # Build schema summary so the agent understands the DataFrame structure
        schema_info = get_dataframe_schema(self.file_path)
        system_prompt = f"{BASE_SYSTEM_PROMPT}\n\n{schema_info}"

        # Initialize tools
        self.math_tool = get_math_tool(file_path=self.file_path)
        self.search_tool = get_search_tool(db_getter=_get_db, project_id=self.project_id)

        # Compile the single ReAct agent graph ONCE
        print(f"[InsightAI] Compiling single ReAct agent for project {project_id}...")
        self.agent = create_react_agent(
            model=self.llm,
            tools=[self.search_tool, self.math_tool],
            prompt=system_prompt,
        )
        print(f"[InsightAI] Agent for project {project_id} ready.")

    def ask_question(self, question: str) -> str:
        """
        Answers a question using the pre-compiled ReAct agent.
        """
        import time
        from app.core.database import SessionLocal

        db = SessionLocal()
        self._local.db = db

        try:
            max_retries = 3

            for attempt in range(max_retries):
                try:
                    response = self.agent.invoke({"messages": [("human", question)]})
                    raw = response["messages"][-1].content
                    # Gemini can return content as a list of parts (e.g. [{"type": "text", "text": "..."}])
                    if isinstance(raw, list):
                        return " ".join(
                            part.get("text", "") for part in raw
                            if isinstance(part, dict)
                        )
                    return raw
                except Exception as e:
                    error_msg = str(e)

                    # Handle Gemini rate limits immediately to prevent server 504 timeouts
                    if "429" in error_msg or "rate limit" in error_msg.lower() or "resource_exhausted" in error_msg.lower():
                        return "Gemini API rate limit reached. Please wait a few seconds before asking your next question."

                    # Handle malformed JSON tool calls from the LLM
                    if "Failed to parse tool call" in error_msg or "JSON" in error_msg:
                        if attempt < max_retries - 1:
                            print(f"[InsightAI] LLM produced invalid JSON, retrying...")
                            time.sleep(1)
                            continue
                        return (
                            "The AI agent made a syntax error while trying to answer your question. "
                            "Please try asking in a slightly different way."
                        )

                    return f"An error occurred while processing your request: {error_msg}"

        finally:
            db.close()
            self._local.db = None
