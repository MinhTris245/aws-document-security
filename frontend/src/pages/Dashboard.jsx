import { useEffect, useMemo, useState } from 'react';
import Navbar from '../components/Navbar';
import api from '../services/api';

const SCAN_STATUS_LABELS = {
  PENDING_SCAN: 'Pending scan',
  CLEAN: 'Clean',
  INFECTED: 'Infected',
  SCAN_FAILED: 'Scan failed',
  UNSCANNED: 'Unscanned',
};

export default function Dashboard() {
  const [docs, setDocs] = useState([]);
  const [incidents, setIncidents] = useState([]);
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [actionId, setActionId] = useState('');
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [pendingDelete, setPendingDelete] = useState(null);
  const [toast, setToast] = useState('');
  const role = localStorage.getItem('role');

  useEffect(() => {
    fetchDashboard();
  }, []);

  const totalStorage = useMemo(
    () => docs.reduce((sum, doc) => sum + Number(doc.size || 0), 0),
    [docs],
  );

  const highIncidents = useMemo(
    () => incidents.filter(item => ['HIGH', 'CRITICAL'].includes(String(item.severity).toUpperCase())).length,
    [incidents],
  );

  const fileTypes = useMemo(
    () => [...new Set(docs.map(doc => doc.file_type).filter(Boolean))].sort(),
    [docs],
  );

  const filteredDocs = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return docs.filter(doc => {
      const name = String(doc.original_name || doc.filename || '').toLowerCase();
      const owner = String(doc.uploader || '').toLowerCase();
      const matchesQuery = !needle || name.includes(needle) || owner.includes(needle);
      const matchesType = !typeFilter || doc.file_type === typeFilter;
      return matchesQuery && matchesType;
    });
  }, [docs, query, typeFilter]);

  async function fetchDashboard() {
    setLoading(true);
    setError('');
    try {
      const [documentsRes, incidentsRes, healthRes] = await Promise.allSettled([
        api.get('/documents'),
        api.get('/incidents?limit=20'),
        api.get('/health'),
      ]);

      if (documentsRes.status === 'fulfilled') setDocs(documentsRes.value.data);
      if (incidentsRes.status === 'fulfilled') setIncidents(incidentsRes.value.data);
      if (healthRes.status === 'fulfilled') setHealth(healthRes.value.data);

      const failed = [documentsRes, incidentsRes, healthRes].filter(item => item.status === 'rejected');
      if (failed.length) {
        setError('Some AWS-backed data could not be loaded. Check .env, S3, and DynamoDB.');
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleDownload(doc) {
    if (!canDownload(doc)) {
      setError('This document cannot be downloaded until the malware scan confirms it is clean.');
      return;
    }

    setActionId(doc.document_id);
    try {
      const res = await api.get(`/documents/download/${doc.document_id}`);
      window.open(res.data.download_url, '_blank', 'noopener,noreferrer');
      setToast('Download link opened');
    } catch (err) {
      setError(err.response?.data?.error || 'Cannot download file');
    } finally {
      setActionId('');
    }
  }

  async function confirmDelete() {
    if (!pendingDelete) return;
    const doc = pendingDelete;
    setActionId(doc.document_id);
    try {
      await api.delete(`/documents/${doc.document_id}`);
      setDocs(docs.filter(item => item.document_id !== doc.document_id));
      setPendingDelete(null);
      setToast('Document deleted');
    } catch (err) {
      setError(err.response?.data?.error || 'Delete failed');
    } finally {
      setActionId('');
    }
  }

  function formatSize(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function formatDate(iso) {
    if (!iso) return '-';
    return new Date(iso).toLocaleString('vi-VN');
  }

  function healthBadge(key, label) {
    const ok = health?.checks?.[key]?.ok;
    return <span className={`status-badge ${ok ? 'ok' : ''}`}>{label}: {ok ? 'OK' : 'Check'}</span>;
  }

  function normalizedScanStatus(doc) {
    return String(doc.scan_status || 'UNSCANNED').toUpperCase();
  }

  function canDownload(doc) {
    return normalizedScanStatus(doc) === 'CLEAN';
  }

  function scanStatusBadge(doc) {
    const status = normalizedScanStatus(doc);
    const label = SCAN_STATUS_LABELS[status] || status;
    return <span className={`status-label ${status.toLowerCase()}`}>{label}</span>;
  }

  return (
    <div className="app-shell">
      <Navbar />
      <main className="page">
        <div className="page-header">
          <div>
            <div className="eyebrow">AWS document management</div>
            <h1 className="page-title">Document Dashboard</h1>
          </div>
          <button className="btn btn-primary" onClick={fetchDashboard} disabled={loading}>
            {loading ? 'Refreshing...' : 'Refresh data'}
          </button>
        </div>

        <div className="row g-3 mb-4">
          <div className="col-md-6 col-xl-3">
            <div className="metric-card metric-blue">
              <div className="metric-label">Documents</div>
              <div className="metric-value">{docs.length}</div>
            </div>
          </div>
          <div className="col-md-6 col-xl-3">
            <div className="metric-card metric-green">
              <div className="metric-label">Stored data</div>
              <div className="metric-value">{formatSize(totalStorage)}</div>
            </div>
          </div>
          <div className="col-md-6 col-xl-3">
            <div className="metric-card metric-red">
              <div className="metric-label">High risk</div>
              <div className="metric-value">{highIncidents}</div>
            </div>
          </div>
          <div className="col-md-6 col-xl-3">
            <div className="metric-card metric-amber">
              <div className="metric-label">AWS health</div>
              <div className="status-row mt-3">
                {healthBadge('s3', 'S3')}
                {healthBadge('documents_table', 'Docs')}
                {healthBadge('incidents_table', 'Incidents')}
              </div>
            </div>
          </div>
        </div>

        {error && <div className="alert alert-warning">{error}</div>}

        <section className="panel">
          <div className="panel-header">
            <div>
              <h2 className="panel-title">Document Inventory</h2>
            </div>
            <a className="btn btn-sm btn-outline-primary" href="/upload">Upload document</a>
          </div>

          {docs.length > 0 && (
            <div className="toolbar-row">
              <div className="toolbar-search">
                <input
                  className="form-control"
                  value={query}
                  onChange={event => setQuery(event.target.value)}
                  placeholder="Search file or owner"
                />
              </div>
              <select className="form-select toolbar-select" value={typeFilter} onChange={event => setTypeFilter(event.target.value)}>
                <option value="">All file types</option>
                {fileTypes.map(type => <option key={type} value={type}>{type.toUpperCase()}</option>)}
              </select>
            </div>
          )}

          {loading && <div className="p-4 text-muted">Loading documents...</div>}

          {!loading && docs.length === 0 && (
            <div className="empty-state">
              <div className="empty-icon">DOC</div>
              <h3>No documents yet</h3>
              <p>Upload a document to start testing S3 storage and DynamoDB metadata.</p>
              <a className="btn btn-primary" href="/upload">Upload document</a>
            </div>
          )}

          {!loading && docs.length > 0 && filteredDocs.length === 0 && (
            <div className="empty-state">
              <div className="empty-icon">FIND</div>
              <h3>No matching documents</h3>
              <p>Try another file name, owner, or type filter.</p>
            </div>
          )}

          {filteredDocs.length > 0 && (
            <div className="table-responsive">
              <table className="table table-hover align-middle">
                <thead>
                  <tr>
                    <th>File</th>
                    <th>Owner</th>
                    <th>Type</th>
                    <th>Size</th>
                    <th>Malware scan</th>
                    <th>Uploaded</th>
                    <th className="text-end">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredDocs.map(doc => (
                    <tr key={doc.document_id}>
                      <td>
                        <div className="file-name">{doc.original_name || doc.filename}</div>
                        <div className="muted-small">{doc.document_id}</div>
                      </td>
                      <td>{doc.uploader}</td>
                      <td><span className="status-label">{doc.file_type || '-'}</span></td>
                      <td>{formatSize(doc.size)}</td>
                      <td>{scanStatusBadge(doc)}</td>
                      <td>{formatDate(doc.uploaded_at)}</td>
                      <td className="text-end">
                        <button
                          className="btn btn-sm btn-primary me-2"
                          onClick={() => handleDownload(doc)}
                          disabled={actionId === doc.document_id || !canDownload(doc)}
                          title={canDownload(doc) ? 'Download clean document' : 'Download is locked until the malware scan reports CLEAN'}
                        >
                          {normalizedScanStatus(doc) === 'PENDING_SCAN' ? 'Scanning...' : 'Download'}
                        </button>
                        {role === 'admin' && (
                          <button
                            className="btn btn-sm btn-outline-danger"
                            onClick={() => setPendingDelete(doc)}
                            disabled={actionId === doc.document_id}
                          >
                            Delete
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {toast && (
          <div className="app-toast" role="status">
            <span>{toast}</span>
            <button className="btn-close" type="button" aria-label="Close" onClick={() => setToast('')} />
          </div>
        )}
      </main>

      {pendingDelete && (
        <div className="modal-backdrop-custom" role="dialog" aria-modal="true" aria-labelledby="delete-title">
          <div className="confirm-modal">
            <h2 id="delete-title" className="panel-title mb-2">Delete document?</h2>
            <p className="text-muted mb-4">
              {pendingDelete.original_name || pendingDelete.filename} will be removed from S3 and DynamoDB metadata.
            </p>
            <div className="d-flex justify-content-end gap-2">
              <button className="btn btn-outline-secondary" onClick={() => setPendingDelete(null)} disabled={actionId === pendingDelete.document_id}>
                Cancel
              </button>
              <button className="btn btn-danger" onClick={confirmDelete} disabled={actionId === pendingDelete.document_id}>
                {actionId === pendingDelete.document_id ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
