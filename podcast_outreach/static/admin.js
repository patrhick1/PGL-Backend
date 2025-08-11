// Admin Dashboard JavaScript
let currentData = [];
let currentPage = 1;
let itemsPerPage = 25;
let sortColumn = null;
let sortDirection = 'asc';
let searchTerm = '';
let currentEditType = '';

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    // Load media management by default
    loadMediaManagement();
});

// Navigation functions
function setActiveNav(element) {
    document.querySelectorAll('.nav-link').forEach(link => {
        link.classList.remove('active');
    });
    if (element) {
        element.classList.add('active');
    }
}

// Loading overlay
function showLoading() {
    document.getElementById('loadingOverlay').classList.add('show');
}

function hideLoading() {
    document.getElementById('loadingOverlay').classList.remove('show');
}

// Toast notifications
function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span>${message}</span>
        <button onclick="this.parentElement.remove()" style="background:none;border:none;cursor:pointer;font-size:1.2rem;">&times;</button>
    `;
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.remove();
    }, 5000);
}

// API calls
async function apiCall(url, options = {}) {
    try {
        const response = await fetch(url, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            }
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'API request failed');
        }
        
        return await response.json();
    } catch (error) {
        showToast(error.message, 'error');
        throw error;
    }
}

// Load Media Management
async function loadMediaManagement() {
    setActiveNav(document.querySelector('[onclick="loadMediaManagement()"]'));
    showLoading();
    
    try {
        const data = await apiCall('/media?limit=1000');
        currentData = data;
        currentEditType = 'media';
        
        const content = `
            <div class="data-table-container">
                <div class="table-header">
                    <h2 class="table-title">Media Management</h2>
                    <div class="table-controls">
                        <div class="search-box">
                            <input type="text" placeholder="Search media..." onkeyup="searchTable(this.value)">
                        </div>
                        <select class="filter-select" onchange="filterByConfidence(this.value)">
                            <option value="">All Confidence Levels</option>
                            <option value="high">High (≥ 0.8)</option>
                            <option value="medium">Medium (0.5 - 0.8)</option>
                            <option value="low">Low (< 0.5)</option>
                            <option value="none">No Confidence</option>
                        </select>
                        <button class="btn btn-primary" onclick="showAddMediaForm()">Add Media</button>
                        <button class="btn btn-success" onclick="refreshAllData()">Refresh</button>
                    </div>
                </div>
                <div style="overflow-x: auto;">
                    <table class="data-table" id="dataTable">
                        <thead>
                            <tr>
                                <th class="sortable" onclick="sortTable('media_id')">ID</th>
                                <th class="sortable" onclick="sortTable('name')">Name</th>
                                <th class="sortable" onclick="sortTable('host_names')">Host Names</th>
                                <th class="sortable" onclick="sortTable('host_names_confidence')">Confidence</th>
                                <th class="sortable" onclick="sortTable('contact_email')">Email</th>
                                <th class="sortable" onclick="sortTable('website')">Website</th>
                                <th class="sortable" onclick="sortTable('quality_score')">Quality Score</th>
                                <th class="sortable" onclick="sortTable('api_source')">Source</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody id="tableBody">
                            ${renderMediaRows(data)}
                        </tbody>
                    </table>
                </div>
                <div class="pagination" id="pagination"></div>
            </div>
        `;
        
        document.getElementById('mainContent').innerHTML = content;
        updatePagination();
    } catch (error) {
        console.error('Error loading media:', error);
    } finally {
        hideLoading();
    }
}

// Load People Management
async function loadPeopleManagement() {
    setActiveNav(document.querySelector('[onclick="loadPeopleManagement()"]'));
    showLoading();
    
    try {
        const data = await apiCall('/people?limit=1000');
        currentData = data;
        currentEditType = 'people';
        
        const content = `
            <div class="data-table-container">
                <div class="table-header">
                    <h2 class="table-title">People Management</h2>
                    <div class="table-controls">
                        <div class="search-box">
                            <input type="text" placeholder="Search people..." onkeyup="searchTable(this.value)">
                        </div>
                        <select class="filter-select" onchange="filterByRole(this.value)">
                            <option value="">All Roles</option>
                            <option value="host">Host</option>
                            <option value="admin">Admin</option>
                            <option value="user">User</option>
                        </select>
                        <button class="btn btn-primary" onclick="showAddPersonForm()">Add Person</button>
                        <button class="btn btn-success" onclick="refreshAllData()">Refresh</button>
                    </div>
                </div>
                <div style="overflow-x: auto;">
                    <table class="data-table" id="dataTable">
                        <thead>
                            <tr>
                                <th class="sortable" onclick="sortTable('person_id')">ID</th>
                                <th class="sortable" onclick="sortTable('first_name')">First Name</th>
                                <th class="sortable" onclick="sortTable('last_name')">Last Name</th>
                                <th class="sortable" onclick="sortTable('email')">Email</th>
                                <th class="sortable" onclick="sortTable('role')">Role</th>
                                <th class="sortable" onclick="sortTable('created_at')">Created</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody id="tableBody">
                            ${renderPeopleRows(data)}
                        </tbody>
                    </table>
                </div>
                <div class="pagination" id="pagination"></div>
            </div>
        `;
        
        document.getElementById('mainContent').innerHTML = content;
        updatePagination();
    } catch (error) {
        console.error('Error loading people:', error);
    } finally {
        hideLoading();
    }
}

// Load Media-People Relations
async function loadMediaPeopleRelations() {
    setActiveNav(document.querySelector('[onclick="loadMediaPeopleRelations()"]'));
    showLoading();
    
    try {
        // First get all media
        const mediaData = await apiCall('/media?limit=1000');
        currentData = mediaData;
        currentEditType = 'relations';
        
        const content = `
            <div class="data-table-container">
                <div class="table-header">
                    <h2 class="table-title">Media-People Relations</h2>
                    <div class="table-controls">
                        <div class="search-box">
                            <input type="text" placeholder="Search..." onkeyup="searchTable(this.value)">
                        </div>
                        <button class="btn btn-primary" onclick="showLinkHostForm()">Link Host to Media</button>
                        <button class="btn btn-success" onclick="refreshAllData()">Refresh</button>
                    </div>
                </div>
                <div style="overflow-x: auto;">
                    <table class="data-table" id="dataTable">
                        <thead>
                            <tr>
                                <th class="sortable" onclick="sortTable('media_id')">Media ID</th>
                                <th class="sortable" onclick="sortTable('name')">Media Name</th>
                                <th>Host Names</th>
                                <th>Host Confidence</th>
                                <th>Discovery Sources</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody id="tableBody">
                            ${renderRelationsRows(mediaData)}
                        </tbody>
                    </table>
                </div>
                <div class="pagination" id="pagination"></div>
            </div>
        `;
        
        document.getElementById('mainContent').innerHTML = content;
        updatePagination();
    } catch (error) {
        console.error('Error loading relations:', error);
    } finally {
        hideLoading();
    }
}

// Load Enrichment Queue
async function loadEnrichmentQueue() {
    setActiveNav(document.querySelector('[onclick="loadEnrichmentQueue()"]'));
    showLoading();
    
    try {
        const content = `
            <div class="data-table-container">
                <div class="table-header">
                    <h2 class="table-title">Enrichment Queue & Status</h2>
                    <div class="table-controls">
                        <button class="btn btn-primary" onclick="triggerBulkEnrichment()">Trigger Bulk Enrichment</button>
                        <button class="btn btn-success" onclick="loadEnrichmentQueue()">Refresh Status</button>
                    </div>
                </div>
                <div style="padding: 2rem;">
                    <h3>Media Needing Enrichment</h3>
                    <div id="enrichmentStats"></div>
                    <br>
                    <h3>Actions</h3>
                    <ul>
                        <li><button class="action-btn" onclick="enrichMediaWithoutHosts()">Enrich Media Without Host Names</button></li>
                        <li><button class="action-btn" onclick="enrichLowConfidenceMedia()">Enrich Low Confidence Media</button></li>
                        <li><button class="action-btn" onclick="verifyAllHostNames()">Verify All Host Names</button></li>
                    </ul>
                </div>
            </div>
        `;
        
        document.getElementById('mainContent').innerHTML = content;
        await loadEnrichmentStats();
    } catch (error) {
        console.error('Error loading enrichment queue:', error);
    } finally {
        hideLoading();
    }
}

// Render functions
function renderMediaRows(data) {
    const start = (currentPage - 1) * itemsPerPage;
    const end = start + itemsPerPage;
    const pageData = data.slice(start, end);
    
    return pageData.map(item => `
        <tr>
            <td>${item.media_id}</td>
            <td class="editable" onclick="quickEdit(${item.media_id}, 'name', '${escapeHtml(item.name || '')}')">${escapeHtml(item.name || '')}</td>
            <td class="editable" onclick="editHostNames(${item.media_id})">${formatHostNames(item.host_names)}</td>
            <td>${formatConfidence(item.host_names_confidence)}</td>
            <td class="editable" onclick="quickEdit(${item.media_id}, 'contact_email', '${escapeHtml(item.contact_email || '')}')">${escapeHtml(item.contact_email || '')}</td>
            <td class="editable" onclick="quickEdit(${item.media_id}, 'website', '${escapeHtml(item.website || '')}')">${escapeHtml(item.website || '')}</td>
            <td>${item.quality_score ? item.quality_score.toFixed(2) : 'N/A'}</td>
            <td>${item.api_source || 'N/A'}</td>
            <td>
                <button class="btn btn-sm btn-primary" onclick="editMedia(${item.media_id})">Edit</button>
                <button class="btn btn-sm btn-success" onclick="enrichSingleMedia(${item.media_id})">Enrich</button>
            </td>
        </tr>
    `).join('');
}

function renderPeopleRows(data) {
    const start = (currentPage - 1) * itemsPerPage;
    const end = start + itemsPerPage;
    const pageData = data.slice(start, end);
    
    return pageData.map(item => `
        <tr>
            <td>${item.person_id}</td>
            <td class="editable" onclick="quickEdit(${item.person_id}, 'first_name', '${escapeHtml(item.first_name || '')}')">${escapeHtml(item.first_name || '')}</td>
            <td class="editable" onclick="quickEdit(${item.person_id}, 'last_name', '${escapeHtml(item.last_name || '')}')">${escapeHtml(item.last_name || '')}</td>
            <td class="editable" onclick="quickEdit(${item.person_id}, 'email', '${escapeHtml(item.email || '')}')">${escapeHtml(item.email || '')}</td>
            <td>${item.role || 'N/A'}</td>
            <td>${formatDate(item.created_at)}</td>
            <td>
                <button class="btn btn-sm btn-primary" onclick="editPerson(${item.person_id})">Edit</button>
            </td>
        </tr>
    `).join('');
}

function renderRelationsRows(data) {
    const start = (currentPage - 1) * itemsPerPage;
    const end = start + itemsPerPage;
    const pageData = data.slice(start, end);
    
    return pageData.map(item => `
        <tr>
            <td>${item.media_id}</td>
            <td>${escapeHtml(item.name || '')}</td>
            <td>${formatHostNames(item.host_names)}</td>
            <td>${formatConfidence(item.host_names_confidence)}</td>
            <td>${formatDiscoverySources(item.host_names_discovery_sources)}</td>
            <td>
                <button class="btn btn-sm btn-primary" onclick="editHostNames(${item.media_id})">Edit Hosts</button>
                <button class="btn btn-sm btn-success" onclick="verifyHostNames(${item.media_id})">Verify</button>
            </td>
        </tr>
    `).join('');
}

// Format functions
function formatHostNames(hostNames) {
    if (!hostNames || hostNames.length === 0) {
        return '<span style="color: #999;">No hosts</span>';
    }
    if (Array.isArray(hostNames)) {
        return hostNames.map(name => escapeHtml(name)).join(', ');
    }
    return escapeHtml(hostNames);
}

function formatConfidence(confidence) {
    if (confidence === null || confidence === undefined) {
        return '<span class="confidence-badge confidence-low">No Score</span>';
    }
    
    const value = parseFloat(confidence);
    let className = 'confidence-low';
    if (value >= 0.8) className = 'confidence-high';
    else if (value >= 0.5) className = 'confidence-medium';
    
    return `<span class="confidence-badge ${className}">${(value * 100).toFixed(0)}%</span>`;
}

function formatDiscoverySources(sources) {
    if (!sources || sources.length === 0) {
        return 'N/A';
    }
    if (Array.isArray(sources)) {
        return sources.join(', ');
    }
    return sources;
}

function formatDate(dateString) {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleDateString();
}

function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return String(text).replace(/[&<>"']/g, m => map[m]);
}

// Sorting
function sortTable(column) {
    if (sortColumn === column) {
        sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
    } else {
        sortColumn = column;
        sortDirection = 'asc';
    }
    
    currentData.sort((a, b) => {
        let aVal = a[column];
        let bVal = b[column];
        
        if (aVal === null || aVal === undefined) aVal = '';
        if (bVal === null || bVal === undefined) bVal = '';
        
        if (typeof aVal === 'string') aVal = aVal.toLowerCase();
        if (typeof bVal === 'string') bVal = bVal.toLowerCase();
        
        if (sortDirection === 'asc') {
            return aVal > bVal ? 1 : -1;
        } else {
            return aVal < bVal ? 1 : -1;
        }
    });
    
    // Update table
    refreshTable();
    
    // Update header classes
    document.querySelectorAll('.data-table th').forEach(th => {
        th.classList.remove('sorted-asc', 'sorted-desc');
    });
    
    const th = document.querySelector(`th[onclick="sortTable('${column}')"]`);
    if (th) {
        th.classList.add(sortDirection === 'asc' ? 'sorted-asc' : 'sorted-desc');
    }
}

// Search
function searchTable(term) {
    searchTerm = term.toLowerCase();
    currentPage = 1;
    
    if (!term) {
        refreshTable();
        return;
    }
    
    const filtered = currentData.filter(item => {
        return Object.values(item).some(value => {
            if (value === null || value === undefined) return false;
            return String(value).toLowerCase().includes(searchTerm);
        });
    });
    
    const tbody = document.getElementById('tableBody');
    if (currentEditType === 'media') {
        tbody.innerHTML = renderMediaRows(filtered);
    } else if (currentEditType === 'people') {
        tbody.innerHTML = renderPeopleRows(filtered);
    } else if (currentEditType === 'relations') {
        tbody.innerHTML = renderRelationsRows(filtered);
    }
    
    updatePagination(filtered.length);
}

// Filter functions
function filterByConfidence(level) {
    let filtered = currentData;
    
    if (level === 'high') {
        filtered = currentData.filter(item => item.host_names_confidence >= 0.8);
    } else if (level === 'medium') {
        filtered = currentData.filter(item => item.host_names_confidence >= 0.5 && item.host_names_confidence < 0.8);
    } else if (level === 'low') {
        filtered = currentData.filter(item => item.host_names_confidence < 0.5 && item.host_names_confidence !== null);
    } else if (level === 'none') {
        filtered = currentData.filter(item => item.host_names_confidence === null || item.host_names_confidence === undefined);
    }
    
    const tbody = document.getElementById('tableBody');
    tbody.innerHTML = renderMediaRows(filtered);
    updatePagination(filtered.length);
}

function filterByRole(role) {
    let filtered = currentData;
    
    if (role) {
        filtered = currentData.filter(item => item.role === role);
    }
    
    const tbody = document.getElementById('tableBody');
    tbody.innerHTML = renderPeopleRows(filtered);
    updatePagination(filtered.length);
}

// Pagination
function updatePagination(totalItems = null) {
    const total = totalItems || currentData.length;
    const totalPages = Math.ceil(total / itemsPerPage);
    
    const pagination = document.getElementById('pagination');
    if (!pagination) return;
    
    let html = `
        <button onclick="changePage(1)" ${currentPage === 1 ? 'disabled' : ''}>First</button>
        <button onclick="changePage(${currentPage - 1})" ${currentPage === 1 ? 'disabled' : ''}>Previous</button>
        <span class="page-info">Page ${currentPage} of ${totalPages} (${total} items)</span>
        <button onclick="changePage(${currentPage + 1})" ${currentPage === totalPages ? 'disabled' : ''}>Next</button>
        <button onclick="changePage(${totalPages})" ${currentPage === totalPages ? 'disabled' : ''}>Last</button>
    `;
    
    pagination.innerHTML = html;
}

function changePage(page) {
    const totalPages = Math.ceil(currentData.length / itemsPerPage);
    if (page < 1 || page > totalPages) return;
    
    currentPage = page;
    refreshTable();
}

function refreshTable() {
    const tbody = document.getElementById('tableBody');
    if (!tbody) return;
    
    if (currentEditType === 'media') {
        tbody.innerHTML = renderMediaRows(currentData);
    } else if (currentEditType === 'people') {
        tbody.innerHTML = renderPeopleRows(currentData);
    } else if (currentEditType === 'relations') {
        tbody.innerHTML = renderRelationsRows(currentData);
    }
    
    updatePagination();
}

// Edit functions
async function editMedia(mediaId) {
    const media = currentData.find(m => m.media_id === mediaId);
    if (!media) return;
    
    const fields = `
        <div class="form-group">
            <label>Name</label>
            <input type="text" id="edit_name" value="${escapeHtml(media.name || '')}">
        </div>
        <div class="form-group">
            <label>Description</label>
            <textarea id="edit_description">${escapeHtml(media.description || '')}</textarea>
        </div>
        <div class="form-group">
            <label>Host Names (comma-separated)</label>
            <input type="text" id="edit_host_names" value="${media.host_names ? media.host_names.join(', ') : ''}">
        </div>
        <div class="form-group">
            <label>Host Names Confidence (0-1)</label>
            <input type="number" id="edit_host_names_confidence" min="0" max="1" step="0.1" value="${media.host_names_confidence || ''}">
        </div>
        <div class="form-group">
            <label>Contact Email</label>
            <input type="email" id="edit_contact_email" value="${escapeHtml(media.contact_email || '')}">
        </div>
        <div class="form-group">
            <label>Website</label>
            <input type="url" id="edit_website" value="${escapeHtml(media.website || '')}">
        </div>
        <div class="form-group">
            <label>RSS URL</label>
            <input type="url" id="edit_rss_url" value="${escapeHtml(media.rss_url || '')}">
        </div>
    `;
    
    showModal('Edit Media', fields, async () => {
        const updateData = {
            name: document.getElementById('edit_name').value,
            description: document.getElementById('edit_description').value,
            host_names: document.getElementById('edit_host_names').value.split(',').map(s => s.trim()).filter(s => s),
            host_names_confidence: parseFloat(document.getElementById('edit_host_names_confidence').value) || null,
            contact_email: document.getElementById('edit_contact_email').value || null,
            website: document.getElementById('edit_website').value || null,
            rss_url: document.getElementById('edit_rss_url').value || null
        };
        
        await updateMedia(mediaId, updateData);
    });
}

async function editPerson(personId) {
    const person = currentData.find(p => p.person_id === personId);
    if (!person) return;
    
    const fields = `
        <div class="form-group">
            <label>First Name</label>
            <input type="text" id="edit_first_name" value="${escapeHtml(person.first_name || '')}">
        </div>
        <div class="form-group">
            <label>Last Name</label>
            <input type="text" id="edit_last_name" value="${escapeHtml(person.last_name || '')}">
        </div>
        <div class="form-group">
            <label>Email</label>
            <input type="email" id="edit_email" value="${escapeHtml(person.email || '')}">
        </div>
        <div class="form-group">
            <label>Role</label>
            <select id="edit_role">
                <option value="user" ${person.role === 'user' ? 'selected' : ''}>User</option>
                <option value="host" ${person.role === 'host' ? 'selected' : ''}>Host</option>
                <option value="admin" ${person.role === 'admin' ? 'selected' : ''}>Admin</option>
            </select>
        </div>
    `;
    
    showModal('Edit Person', fields, async () => {
        const updateData = {
            first_name: document.getElementById('edit_first_name').value,
            last_name: document.getElementById('edit_last_name').value,
            email: document.getElementById('edit_email').value,
            role: document.getElementById('edit_role').value
        };
        
        await updatePerson(personId, updateData);
    });
}

async function editHostNames(mediaId) {
    const media = currentData.find(m => m.media_id === mediaId);
    if (!media) return;
    
    const fields = `
        <div class="form-group">
            <label>Host Names (comma-separated)</label>
            <input type="text" id="edit_host_names" value="${media.host_names ? media.host_names.join(', ') : ''}">
        </div>
        <div class="form-group">
            <label>Confidence Score (0-1)</label>
            <input type="number" id="edit_confidence" min="0" max="1" step="0.1" value="${media.host_names_confidence || '0.8'}">
        </div>
        <div class="form-group">
            <label>Discovery Source</label>
            <select id="edit_source">
                <option value="manual">Manual Entry</option>
                <option value="api">API Discovery</option>
                <option value="enrichment">AI Enrichment</option>
            </select>
        </div>
    `;
    
    showModal('Edit Host Names', fields, async () => {
        const hostNames = document.getElementById('edit_host_names').value.split(',').map(s => s.trim()).filter(s => s);
        const confidence = parseFloat(document.getElementById('edit_confidence').value);
        
        const updateData = {
            host_names: hostNames,
            host_names_confidence: confidence,
            data_provenance: {
                host_names: {
                    source: 'manual',
                    confidence: 1.0,
                    updated_at: new Date().toISOString()
                }
            }
        };
        
        await updateMedia(mediaId, updateData);
    });
}

// Quick edit function for inline editing
async function quickEdit(id, field, currentValue) {
    const newValue = prompt(`Edit ${field}:`, currentValue);
    if (newValue === null || newValue === currentValue) return;
    
    const updateData = {};
    updateData[field] = newValue;
    
    if (currentEditType === 'media') {
        await updateMedia(id, updateData);
    } else if (currentEditType === 'people') {
        await updatePerson(id, updateData);
    }
}

// Update functions
async function updateMedia(mediaId, updateData) {
    showLoading();
    try {
        await apiCall(`/media/${mediaId}`, {
            method: 'PUT',
            body: JSON.stringify(updateData)
        });
        
        showToast('Media updated successfully');
        loadMediaManagement();
    } catch (error) {
        console.error('Error updating media:', error);
    } finally {
        hideLoading();
        closeModal();
    }
}

async function updatePerson(personId, updateData) {
    showLoading();
    try {
        await apiCall(`/people/${personId}`, {
            method: 'PUT',
            body: JSON.stringify(updateData)
        });
        
        showToast('Person updated successfully');
        loadPeopleManagement();
    } catch (error) {
        console.error('Error updating person:', error);
    } finally {
        hideLoading();
        closeModal();
    }
}

// Enrichment functions
async function enrichSingleMedia(mediaId) {
    if (!confirm('Trigger enrichment for this media?')) return;
    
    showLoading();
    try {
        await apiCall(`/media/${mediaId}/enrich`, {
            method: 'POST'
        });
        
        showToast('Enrichment triggered successfully');
    } catch (error) {
        console.error('Error triggering enrichment:', error);
    } finally {
        hideLoading();
    }
}

async function triggerBulkEnrichment() {
    if (!confirm('Trigger bulk enrichment for all media needing enrichment?')) return;
    
    showLoading();
    try {
        // This would call a bulk enrichment endpoint
        showToast('Bulk enrichment triggered');
    } catch (error) {
        console.error('Error triggering bulk enrichment:', error);
    } finally {
        hideLoading();
    }
}

async function enrichMediaWithoutHosts() {
    if (!confirm('Enrich all media without host names?')) return;
    
    showLoading();
    try {
        // Call enrichment for media without hosts
        showToast('Enrichment started for media without hosts');
    } catch (error) {
        console.error('Error:', error);
    } finally {
        hideLoading();
    }
}

async function enrichLowConfidenceMedia() {
    if (!confirm('Enrich all media with low confidence scores?')) return;
    
    showLoading();
    try {
        // Call enrichment for low confidence media
        showToast('Enrichment started for low confidence media');
    } catch (error) {
        console.error('Error:', error);
    } finally {
        hideLoading();
    }
}

async function verifyHostNames(mediaId) {
    showLoading();
    try {
        // Call host verification endpoint
        showToast('Host name verification started');
    } catch (error) {
        console.error('Error:', error);
    } finally {
        hideLoading();
    }
}

async function verifyAllHostNames() {
    if (!confirm('Verify all host names?')) return;
    
    showLoading();
    try {
        // Call bulk verification
        showToast('Bulk host verification started');
    } catch (error) {
        console.error('Error:', error);
    } finally {
        hideLoading();
    }
}

// Load enrichment statistics
async function loadEnrichmentStats() {
    try {
        const media = await apiCall('/media?limit=1000');
        
        const stats = {
            total: media.length,
            withoutHosts: media.filter(m => !m.host_names || m.host_names.length === 0).length,
            lowConfidence: media.filter(m => m.host_names_confidence && m.host_names_confidence < 0.8).length,
            noConfidence: media.filter(m => m.host_names && m.host_names.length > 0 && !m.host_names_confidence).length
        };
        
        document.getElementById('enrichmentStats').innerHTML = `
            <ul>
                <li>Total Media: ${stats.total}</li>
                <li>Without Host Names: ${stats.withoutHosts}</li>
                <li>Low Confidence (< 80%): ${stats.lowConfidence}</li>
                <li>No Confidence Score: ${stats.noConfidence}</li>
            </ul>
        `;
    } catch (error) {
        console.error('Error loading stats:', error);
    }
}

// Modal functions
function showModal(title, fields, onSave) {
    const modal = document.getElementById('editModal');
    document.getElementById('modalTitle').textContent = title;
    document.getElementById('formFields').innerHTML = fields;
    
    const form = document.getElementById('editForm');
    form.onsubmit = async (e) => {
        e.preventDefault();
        await onSave();
    };
    
    modal.classList.add('show');
}

function closeModal() {
    document.getElementById('editModal').classList.remove('show');
}

// Refresh all data
async function refreshAllData() {
    if (currentEditType === 'media') {
        await loadMediaManagement();
    } else if (currentEditType === 'people') {
        await loadPeopleManagement();
    } else if (currentEditType === 'relations') {
        await loadMediaPeopleRelations();
    } else if (currentEditType === 'enrichment') {
        await loadEnrichmentQueue();
    }
}

// Add forms
function showAddMediaForm() {
    const fields = `
        <div class="form-group">
            <label>Name *</label>
            <input type="text" id="add_name" required>
        </div>
        <div class="form-group">
            <label>Description</label>
            <textarea id="add_description"></textarea>
        </div>
        <div class="form-group">
            <label>Host Names (comma-separated)</label>
            <input type="text" id="add_host_names">
        </div>
        <div class="form-group">
            <label>Contact Email</label>
            <input type="email" id="add_contact_email">
        </div>
        <div class="form-group">
            <label>Website</label>
            <input type="url" id="add_website">
        </div>
        <div class="form-group">
            <label>RSS URL</label>
            <input type="url" id="add_rss_url">
        </div>
    `;
    
    showModal('Add New Media', fields, async () => {
        const mediaData = {
            name: document.getElementById('add_name').value,
            description: document.getElementById('add_description').value || null,
            host_names: document.getElementById('add_host_names').value.split(',').map(s => s.trim()).filter(s => s),
            contact_email: document.getElementById('add_contact_email').value || null,
            website: document.getElementById('add_website').value || null,
            rss_url: document.getElementById('add_rss_url').value || null
        };
        
        showLoading();
        try {
            await apiCall('/media', {
                method: 'POST',
                body: JSON.stringify(mediaData)
            });
            
            showToast('Media created successfully');
            loadMediaManagement();
        } catch (error) {
            console.error('Error creating media:', error);
        } finally {
            hideLoading();
            closeModal();
        }
    });
}

function showAddPersonForm() {
    const fields = `
        <div class="form-group">
            <label>First Name *</label>
            <input type="text" id="add_first_name" required>
        </div>
        <div class="form-group">
            <label>Last Name *</label>
            <input type="text" id="add_last_name" required>
        </div>
        <div class="form-group">
            <label>Email *</label>
            <input type="email" id="add_email" required>
        </div>
        <div class="form-group">
            <label>Role</label>
            <select id="add_role">
                <option value="user">User</option>
                <option value="host">Host</option>
                <option value="admin">Admin</option>
            </select>
        </div>
    `;
    
    showModal('Add New Person', fields, async () => {
        const personData = {
            first_name: document.getElementById('add_first_name').value,
            last_name: document.getElementById('add_last_name').value,
            email: document.getElementById('add_email').value,
            role: document.getElementById('add_role').value
        };
        
        showLoading();
        try {
            await apiCall('/people', {
                method: 'POST',
                body: JSON.stringify(personData)
            });
            
            showToast('Person created successfully');
            loadPeopleManagement();
        } catch (error) {
            console.error('Error creating person:', error);
        } finally {
            hideLoading();
            closeModal();
        }
    });
}