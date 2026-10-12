import { useState, useMemo, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';

export default function SpreadsheetViewer({ project, onClose }) {
  const [data, setData] = useState({ sheets: [] });
  const [activeSheetIndex, setActiveSheetIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Search & Filter state
  const [searchTerm, setSearchTerm] = useState('');
  const [sortConfig, setSortConfig] = useState({ key: null, direction: 'asc' }); // 'asc', 'desc'
  const [activeFilters, setActiveFilters] = useState({}); // { colName: Set(selectedValues) }
  const [openFilterDropdown, setOpenFilterDropdown] = useState(null); // colName
  const [filterSearchTerms, setFilterSearchTerms] = useState({}); // { colName: searchString }

  // Chat/AI State
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [chatMessages, setChatMessages] = useState([
    { role: 'system', text: 'Hello! I am InsightAI. I can analyze this spreadsheet and answer your questions using the Math and Semantic engines.' }
  ]);
  const [chatInput, setChatInput] = useState('');
  const [isChatLoading, setIsChatLoading] = useState(false);
  const chatEndRef = useRef(null);

  // Pagination state
  const [currentPage, setCurrentPage] = useState(1);
  const [rowsPerPage, setRowsPerPage] = useState(50);

  const dropdownRef = useRef(null);

  // Fetch project data
  useEffect(() => {
    const fetchProjectData = async () => {
      try {
        setLoading(true);
        // We dynamic import api to prevent load order issues
        const { api } = await import('../services/api');
        const res = await api.getProjectData(project.id);
        setData(res);
      } catch (err) {
        setError(err.message || 'Failed to load spreadsheet data');
      } finally {
        setLoading(false);
      }
    };
    fetchProjectData();
  }, [project.id]);

  // Auto-scroll chat to bottom
  useEffect(() => {
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [chatMessages, isChatOpen]);

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!chatInput.trim()) return;

    const userMsg = chatInput.trim();
    setChatMessages(prev => [...prev, { role: 'user', text: userMsg }]);
    setChatInput('');
    setIsChatLoading(true);

    try {
      const { api } = await import('../services/api');
      const res = await api.chatWithProject(project.id, userMsg);
      setChatMessages(prev => [...prev, { role: 'system', text: res.answer }]);
    } catch (err) {
      setChatMessages(prev => [...prev, { role: 'system', text: `Error: ${err.message}` }]);
    } finally {
      setIsChatLoading(false);
    }
  };

  // Click outside to close column filter dropdowns
  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setOpenFilterDropdown(null);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Memoized so hooks below only re-run when the data or active sheet actually changes
  const currentSheet = useMemo(
    () => (data.sheets && data.sheets.length > 0 ? data.sheets[activeSheetIndex] : { headers: [], rows: [] }),
    [data, activeSheetIndex]
  );

  // Compute unique values for each column for the Excel filters
  const uniqueColumnValues = useMemo(() => {
    const values = {};
    if (!currentSheet.headers) return values;

    currentSheet.headers.forEach(header => {
      const unique = new Set();
      currentSheet.rows.forEach(row => {
        const val = row[header];
        unique.add(val === null || val === undefined ? '(Blank)' : String(val));
      });
      values[header] = Array.from(unique).sort((a, b) =>
        a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' })
      );
    });
    return values;
  }, [currentSheet]);

  // Initialize filters with all values selected when data or sheet changes
  useEffect(() => {
    if (currentSheet.headers && currentSheet.headers.length > 0) {
      const initial = {};
      currentSheet.headers.forEach(header => {
        initial[header] = new Set(uniqueColumnValues[header]);
      });
      setActiveFilters(initial);
      setSearchTerm('');
      setSortConfig({ key: null, direction: 'asc' });
      setCurrentPage(1);
    }
  }, [currentSheet, uniqueColumnValues]);

  // Handle filter checkbox toggle
  const handleFilterToggle = (column, value) => {
    setActiveFilters(prev => {
      const next = { ...prev };
      const currentSet = new Set(next[column]);
      if (currentSet.has(value)) {
        currentSet.delete(value);
      } else {
        currentSet.add(value);
      }
      next[column] = currentSet;
      return next;
    });
    setCurrentPage(1);
  };

  // Toggle "Select All" for a column's filters
  const handleSelectAllToggle = (column) => {
    const allVals = uniqueColumnValues[column];
    const currentSet = activeFilters[column];
    const isAllSelected = currentSet && currentSet.size === allVals.length;

    setActiveFilters(prev => {
      const next = { ...prev };
      next[column] = isAllSelected ? new Set() : new Set(allVals);
      return next;
    });
    setCurrentPage(1);
  };

  // Check if a filter is currently active (i.e. not all values selected)
  const isColumnFiltered = (column) => {
    const currentSet = activeFilters[column];
    const allVals = uniqueColumnValues[column];
    return currentSet && currentSet.size < allVals.length;
  };

  // Handle Sort config
  const requestSort = (key) => {
    let direction = 'asc';
    if (sortConfig.key === key && sortConfig.direction === 'asc') {
      direction = 'desc';
    }
    setSortConfig({ key, direction });
    setCurrentPage(1);
  };

  // Process rows: Filter -> Search -> Sort
  const processedRows = useMemo(() => {
    if (!currentSheet.rows) return [];
    let rows = [...currentSheet.rows];

    // 1. Column Filters
    currentSheet.headers.forEach(header => {
      const allowed = activeFilters[header];
      if (allowed) {
        rows = rows.filter(row => {
          const val = row[header];
          const valStr = val === null || val === undefined ? '(Blank)' : String(val);
          return allowed.has(valStr);
        });
      }
    });

    // 2. Global Search
    if (searchTerm.trim() !== '') {
      const term = searchTerm.toLowerCase();
      rows = rows.filter(row => {
        return Object.values(row).some(val =>
          val !== null && val !== undefined && String(val).toLowerCase().includes(term)
        );
      });
    }

    // 3. Sorting
    if (sortConfig.key !== null) {
      const { key, direction } = sortConfig;
      rows.sort((a, b) => {
        const valA = a[key] === null || a[key] === undefined ? '' : a[key];
        const valB = b[key] === null || b[key] === undefined ? '' : b[key];

        // Numeric sort if possible
        const numA = Number(valA);
        const numB = Number(valB);
        if (!isNaN(numA) && !isNaN(numB) && valA !== '' && valB !== '') {
          return direction === 'asc' ? numA - numB : numB - numA;
        }

        // String sort
        const strA = String(valA);
        const strB = String(valB);
        return direction === 'asc'
          ? strA.localeCompare(strB, undefined, { numeric: true })
          : strB.localeCompare(strA, undefined, { numeric: true });
      });
    }

    return rows;
  }, [currentSheet, searchTerm, sortConfig, activeFilters]);

  // Pagination calculation
  const totalPages = Math.ceil(processedRows.length / rowsPerPage) || 1;
  const paginatedRows = useMemo(() => {
    const startIndex = (currentPage - 1) * rowsPerPage;
    return processedRows.slice(startIndex, startIndex + rowsPerPage);
  }, [processedRows, currentPage, rowsPerPage]);

  const resetAllFilters = () => {
    setSearchTerm('');
    setSortConfig({ key: null, direction: 'asc' });
    const resetFilters = {};
    currentSheet.headers.forEach(header => {
      resetFilters[header] = new Set(uniqueColumnValues[header]);
    });
    setActiveFilters(resetFilters);
    setCurrentPage(1);
  };

  const getActiveFiltersCount = () => {
    let count = 0;
    if (!currentSheet.headers) return 0;
    currentSheet.headers.forEach(header => {
      if (isColumnFiltered(header)) count++;
    });
    if (searchTerm) count++;
    if (sortConfig.key) count++;
    return count;
  };

  if (loading) {
    return (
      <div className="viewer-overlay">
        <div className="viewer-container loading-state">
          <div className="spinner"></div>
          <p>Processing and rendering spreadsheet data...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="viewer-overlay">
      <div className={`viewer-content-wrapper ${isChatOpen ? 'chat-open' : ''}`}>
        <div className="viewer-container">

          {/* Header toolbar */}
          <header className="viewer-header">
            <div className="header-info">
              <span className="file-icon">📊</span>
              <div>
                <h3>{project.name}</h3>
                <p className="subtitle">{project.file_name} • {currentSheet.rows?.length || 0} rows</p>
              </div>
            </div>

            <div className="header-actions">
              <button
                className={`ai-toggle-btn ${isChatOpen ? 'active' : ''}`}
                onClick={() => setIsChatOpen(!isChatOpen)}
              >
                ✨ InsightAI
              </button>
              {getActiveFiltersCount() > 0 && (
                <button className="reset-filters-btn" onClick={resetAllFilters}>
                  Clear Active Filters ({getActiveFiltersCount()})
                </button>
              )}
              <input
                type="text"
                className="search-input"
                placeholder="Search spreadsheet..."
                value={searchTerm}
                onChange={(e) => {
                  setSearchTerm(e.target.value);
                  setCurrentPage(1);
                }}
              />
              <button className="close-btn" onClick={onClose}>Close Viewer</button>
            </div>
          </header>

          {error ? (
            <div className="viewer-error">
              <p className="error-msg">{error}</p>
              <button className="primary-btn" onClick={onClose}>Go Back</button>
            </div>
          ) : (
            <>
              {/* Table viewport */}
              <div className="table-viewport">
                <table className="excel-table">
                  <thead>
                    <tr>
                      <th className="row-num-col">#</th>
                      {currentSheet.headers?.map((header) => {
                        const isFiltered = isColumnFiltered(header);
                        const isSorted = sortConfig.key === header;
                        return (
                          <th key={header} className={isSorted ? 'sorted-th' : ''}>
                            <div className="th-content">
                              <span className="th-title" onClick={() => requestSort(header)}>
                                {header}
                                {isSorted && (sortConfig.direction === 'asc' ? ' 🔼' : ' 🔽')}
                              </span>

                              {/* Filter Dropdown trigger */}
                              <div className="filter-wrapper" ref={openFilterDropdown === header ? dropdownRef : null}>
                                <button
                                  className={`filter-trigger-btn ${isFiltered ? 'active-filter' : ''}`}
                                  onClick={() => setOpenFilterDropdown(openFilterDropdown === header ? null : header)}
                                  title="Filter column"
                                >
                                  ▼
                                </button>

                                {/* Filter Dropdown Menu */}
                                {openFilterDropdown === header && (
                                  <div className="filter-dropdown">
                                    <div className="filter-dropdown-search">
                                      <input
                                        type="text"
                                        placeholder="Search values..."
                                        value={filterSearchTerms[header] || ''}
                                        onChange={(e) => setFilterSearchTerms({
                                          ...filterSearchTerms,
                                          [header]: e.target.value
                                        })}
                                      />
                                    </div>
                                    <div className="filter-dropdown-actions">
                                      <button
                                        type="button"
                                        onClick={() => handleSelectAllToggle(header)}
                                      >
                                        {activeFilters[header]?.size === uniqueColumnValues[header].length
                                          ? 'Deselect All'
                                          : 'Select All'}
                                      </button>
                                    </div>
                                    <div className="filter-dropdown-list">
                                      {uniqueColumnValues[header]
                                        .filter(val =>
                                          val.toLowerCase().includes((filterSearchTerms[header] || '').toLowerCase())
                                        )
                                        .map(val => {
                                          const isChecked = activeFilters[header]?.has(val);
                                          return (
                                            <label key={val} className="filter-checkbox-label">
                                              <input
                                                type="checkbox"
                                                checked={isChecked}
                                                onChange={() => handleFilterToggle(header, val)}
                                              />
                                              <span className="checkbox-custom-label">{val}</span>
                                            </label>
                                          );
                                        })}
                                    </div>
                                  </div>
                                )}
                              </div>
                            </div>
                          </th>
                        );
                      })}
                    </tr>
                  </thead>
                  <tbody>
                    {paginatedRows.length === 0 ? (
                      <tr>
                        <td colSpan={(currentSheet.headers?.length || 0) + 1} className="no-rows">
                          No rows match current search, filters, or sorting configuration.
                        </td>
                      </tr>
                    ) : (
                      paginatedRows.map((row, index) => {
                        const absoluteIndex = (currentPage - 1) * rowsPerPage + index + 1;
                        return (
                          <tr key={index}>
                            <td className="row-num-cell">{absoluteIndex}</td>
                            {currentSheet.headers?.map(header => {
                              const val = row[header];
                              return (
                                <td key={header} className={val === null || val === undefined ? 'empty-cell' : ''}>
                                  {val === null || val === undefined ? '' : String(val)}
                                </td>
                              );
                            })}
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>

              {/* Sheet Tabs at Bottom */}
              {data.sheets && data.sheets.length > 1 && (
                <div className="sheet-tabs-container">
                  {data.sheets.map((sheet, idx) => (
                    <button
                      key={idx}
                      className={`sheet-tab ${idx === activeSheetIndex ? 'active' : ''}`}
                      onClick={() => setActiveSheetIndex(idx)}
                    >
                      {sheet.name}
                    </button>
                  ))}
                </div>
              )}

              {/* Footer / Pagination Toolbar */}
              <footer className="viewer-footer">
                <div className="footer-status">
                  Showing {Math.min(processedRows.length, (currentPage - 1) * rowsPerPage + 1)}-{Math.min(processedRows.length, currentPage * rowsPerPage)} of {processedRows.length} filtered rows (Total: {currentSheet.rows?.length || 0})
                </div>

                <div className="footer-pagination">
                  <div className="page-size-selector">
                    <span>Rows per page:</span>
                    <select
                      value={rowsPerPage}
                      onChange={(e) => {
                        setRowsPerPage(Number(e.target.value));
                        setCurrentPage(1);
                      }}
                    >
                      <option value={20}>20</option>
                      <option value={50}>50</option>
                      <option value={100}>100</option>
                      <option value={500}>500</option>
                    </select>
                  </div>

                  <div className="pagination-controls">
                    <button
                      disabled={currentPage === 1}
                      onClick={() => setCurrentPage(1)}
                    >
                      ⏮️
                    </button>
                    <button
                      disabled={currentPage === 1}
                      onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))}
                    >
                      ◀️
                    </button>
                    <span className="page-indicator">
                      Page {currentPage} of {totalPages}
                    </span>
                    <button
                      disabled={currentPage === totalPages}
                      onClick={() => setCurrentPage(prev => Math.min(prev + 1, totalPages))}
                    >
                      ▶️
                    </button>
                    <button
                      disabled={currentPage === totalPages}
                      onClick={() => setCurrentPage(totalPages)}
                    >
                      ⏭️
                    </button>
                  </div>
                </div>
              </footer>
            </>
          )}
        </div>

        {isChatOpen && (
          <div className="chat-sidebar">
            <div className="chat-header">
              <h3>✨ InsightAI</h3>
              <button className="close-btn-small" onClick={() => setIsChatOpen(false)}>✕</button>
            </div>

            <div className="chat-messages">
              {chatMessages.map((msg, idx) => (
                <div key={idx} className={`chat-bubble ${msg.role}`}>
                  {msg.role === 'system' ? (
                    <div className="chat-markdown">
                      <ReactMarkdown>{msg.text}</ReactMarkdown>
                    </div>
                  ) : (
                    <p>{msg.text}</p>
                  )}
                </div>
              ))}
              {isChatLoading && (
                <div className="chat-bubble system loading">
                  <div className="typing-indicator">
                    <span></span><span></span><span></span>
                  </div>
                  <p>AI is thinking...</p>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>

            <form className="chat-input-area" onSubmit={handleSendMessage}>
              <input
                type="text"
                placeholder="Ask a question about the data..."
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                disabled={isChatLoading}
              />
              <button type="submit" disabled={isChatLoading || !chatInput.trim()}>
                ➤
              </button>
            </form>
          </div>
        )}
      </div>
    </div>
  );
}
