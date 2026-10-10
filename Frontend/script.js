    const configuredApiUrl = window.DISASTERLENS_API_URL?.replace(/\/$/, '');
    const isLocalFrontend = window.location.protocol === 'file:'
      || (['localhost', '127.0.0.1'].includes(window.location.hostname)
        && window.location.port !== '8001');
    const apiBaseUrl = configuredApiUrl ?? (isLocalFrontend ? 'http://127.0.0.1:8001' : '');
    let reports = [];
    let loadingIncidents = true;
    const map = L.map('map', { zoomControl: false, scrollWheelZoom: false }).setView([27.7172, 85.324], 10);
    const tileLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' }).addTo(map);
    L.control.zoom({ position: 'bottomright' }).addTo(map);
    const markerLayer = L.layerGroup().addTo(map);
    const markerById = new Map();
    let selectedId = reports[0]?.id || null;
    let activeFilter = 'all';
    let activeType = 'all';
    let activeSeverity = 'all';
    let activeStatus = 'all';
    let urgencyFirst = true;
    let heatLayer = null;
    const mapRegion = { south: 26, north: 31, west: 79, east: 89 };
    const severityRank = { critical: 4, high: 3, medium: 2, low: 1, unknown: 0 };
    const iconFor = (type) => ({ flood: 'waves', landslide: 'mountain', fire: 'flame', earthquake: 'activity', road_blockage: 'construction', medical: 'heart-pulse', other: 'triangle-alert' }[String(type).toLowerCase().replace(/[\s-]+/g, '_')] || 'triangle-alert');
    const urgencyClass = (value) => ['critical', 'high', 'medium', 'low'].includes(value) ? value : 'unknown';
    const hasCoordinates = (report) => Number.isFinite(report.lat) && Number.isFinite(report.lng);
    const isInMapRegion = (report) => hasCoordinates(report)
      && report.lat >= mapRegion.south && report.lat <= mapRegion.north
      && report.lng >= mapRegion.west && report.lng <= mapRegion.east;

    function normalizePeopleTrapped(value) {
      const normalized = String(value ?? 'unknown').trim().toLowerCase();
      if (['yes', 'true', '1', 'confirmed'].includes(normalized)) return 'yes';
      if (['no', 'false', '0', 'none'].includes(normalized)) return 'no';
      return 'unknown';
    }
    function normalizeRescueStatus(item) {
      if (item.people_rescued === true) return 'rescued';
      if (item.people_rescued === false) return 'awaiting';
      const value = item.rescue_status ?? item.rescue_outcome ?? item.rescueStatus;
      if (value === undefined || value === null || value === '') return null;
      const normalized = String(value).trim().toLowerCase().replace(/[\s-]+/g, '_');
      if (['rescued', 'confirmed_rescued', 'completed', 'safe'].includes(normalized)) return 'rescued';
      if (['underway', 'in_progress', 'en_route', 'active'].includes(normalized)) return 'underway';
      if (['not_required', 'no_rescue_required', 'not_needed'].includes(normalized)) return 'not_required';
      if (['awaiting', 'awaiting_confirmation', 'pending', 'not_yet_confirmed', 'not_rescued'].includes(normalized)) return 'awaiting';
      return 'unknown';
    }
    function rescueOutcome(report) {
      if (report.rescueStatus === 'rescued') return { label: 'Confirmed rescued', state: 'rescued' };
      if (report.rescueStatus === 'underway') return { label: 'Response underway', state: 'underway' };
      if (report.rescueStatus === 'unknown') return { label: 'Unknown', state: 'unknown' };
      if (report.rescueStatus === 'not_required' || report.peopleTrapped === 'no') return { label: 'No rescue indicated', state: 'not-required' };
      if (report.peopleTrapped === 'yes') return { label: 'Awaiting confirmation', state: 'awaiting' };
      return { label: 'Unknown', state: 'unknown' };
    }
    const markerIcon = (report) => L.divIcon({ className: '', html: `<div class="map-pin ${urgencyClass(report.severity)}"><span>${({ critical: '!', high: 'H', medium: 'M', low: 'L', unknown: '?' })[urgencyClass(report.severity)]}</span></div>`, iconSize: [28, 34], iconAnchor: [14, 30], popupAnchor: [0, -28] });
    let selectedPreviewUrl = null;

    function getAnalysisLabel(status) {
      return ({
        completed: 'AI model',
        mock: 'Fallback · verify',
        pending: 'Analysis pending',
        failed: 'Analysis failed'
      })[status] || 'Analysis status unknown';
    }

    function getImageUrl(path) {
      return path?.startsWith('http') ? path : path ? `${apiBaseUrl}${path}` : null;
    }

    function incidentGroups() {
      const groups = new Map();
      reports.forEach((report) => {
        const rootId = report.duplicateOf ?? report.id;
        if (!groups.has(rootId)) groups.set(rootId, []);
        groups.get(rootId).push(report);
      });
      return [...groups.values()];
    }
    function groupedReports(items) {
      const groups = new Map();
      items.forEach((report) => {
        const rootId = report.duplicateOf ?? report.id;
        if (!groups.has(rootId)) groups.set(rootId, []);
        groups.get(rootId).push(report);
      });
      return [...groups.entries()].map(([rootId, members]) => {
        const corroborating = reports.filter((report) => report.id === rootId || report.duplicateOf === rootId);
        const representative = members.find((report) => report.id === rootId) || members[0];
        return { rootId, members: corroborating, representative };
      });
    }

    function sortedReports(severityFirst = false) {
      return [...reports].sort((left, right) => {
        const urgencyScore = (right.urgencyScore ?? -1) - (left.urgencyScore ?? -1);
        const urgency = severityRank[right.severity] - severityRank[left.severity];
        const timeOrder = (right.receivedAt ?? 0) - (left.receivedAt ?? 0);
        if (severityFirst) return urgency || urgencyScore || timeOrder;
        return urgencyFirst ? urgencyScore || urgency || timeOrder : timeOrder;
      });
    }
    function visibleReports() {
      return sortedReports(activeFilter === 'urgent').filter((report) => {
        if (activeFilter === 'urgent' && !['critical', 'high'].includes(report.severity)) return false;
        if (activeFilter === 'duplicate' && report.duplicate !== true) return false;
        return (activeType === 'all' || report.typeKey === activeType)
          && (activeSeverity === 'all' || report.severity === activeSeverity)
          && (activeStatus === 'all' || report.status === activeStatus);
      });
    }
    function renderMarkers() {
      const mappedReports = groupedReports(visibleReports())
        .map((group) => group.representative)
        .filter(isInMapRegion);
      const mapEmpty = document.getElementById('mapEmpty');
      mapEmpty.hidden = mappedReports.length > 0;
      const apiFailed = document.getElementById('apiStatus').dataset.state === 'error';
      document.getElementById('map').dataset.state = apiFailed ? 'error' : mappedReports.length ? 'ready' : loadingIncidents ? 'loading' : 'empty';
      document.getElementById('mapEmptyTitle').textContent = reports.length ? 'No matching reports in the Nepal map area' : 'No incidents yet';
      document.getElementById('mapEmptyDescription').textContent = apiFailed ? 'The Nepal map is ready for new report locations.' : reports.length ? 'Change the incident filters or report locations to show map pins.' : 'New report locations will appear on the map.';
      document.getElementById('map').classList.toggle('map-has-data', mappedReports.length > 0);
      const mapAction = document.getElementById('mapEmptyAction');
      mapAction.dataset.mapAction = apiFailed ? 'retry' : 'report';
      mapAction.innerHTML = apiFailed ? '<i data-lucide="refresh-cw"></i> Refresh feed' : '<i data-lucide="plus"></i> Add report';
      if (window.lucide) lucide.createIcons();
      markerLayer.clearLayers();
      markerById.clear();
      mappedReports.forEach((report) => {
        const group = groupedReports([report])[0];
        const corroboration = group.members.length > 1 ? `<br>${group.members.length} corroborating reports` : '';
        const marker = L.marker([report.lat, report.lng], { icon: markerIcon(report) }).bindPopup(`<div class="popup-title">${escapeHtml(report.type)} · ${report.severity.toUpperCase()}</div><div class="popup-sub">${escapeHtml(report.location)}<br>${escapeHtml(report.title)}${corroboration}</div>`);
        marker.on('click', () => selectIncident(report.id, false));
        marker.addTo(markerLayer);
        markerById.set(report.id, marker);
      });
      refreshHeatLayer();
    }
    function renderQueue() {
      const list = document.getElementById('incidentList');
      const shown = visibleReports();
      list.classList.toggle('is-empty', shown.length === 0);
      let queueContent;
      if (shown.length) {
        queueContent = groupedReports(shown).map(({ members, representative: report }) => {
        const duplicateScore = Math.max(...members.map((member) => member.duplicateConfidence ?? 0));
        const meta = [
          { label: report.time, title: 'Time since this report was received.' },
          { label: getAnalysisLabel(report.analysisStatus), title: report.analysisStatus === 'mock' ? 'No completed live model analysis was recorded. Treat this preliminary assessment as unverified.' : 'Processing status of the report analysis.' },
          report.urgencyScore === null ? null : { label: `Priority ${report.urgencyScore}/100`, title: 'Triage score based on reported severity and needs; it is not a probability.' },
          report.analysisStatus === 'completed' && report.confidence !== null ? { label: `Model confidence ${report.confidence}%`, title: 'The model’s estimate of its own answer quality; this is not a calibrated probability.' } : null,
          members.length > 1 ? { label: `${members.length} independent reports${duplicateScore ? ` · ${Math.round(duplicateScore * 100)}% match` : ''}`, title: report.duplicateReason || 'Reports grouped as possibly describing the same incident.' } : null
        ].filter(Boolean);
        const imageUrl = getImageUrl(report.imageUrl);
        const photo = imageUrl ? `<img class="incident-thumbnail" src="${escapeHtml(imageUrl)}" alt="Photo attached to report ${escapeHtml(report.id)}" loading="lazy">` : '';
        return `<button class="incident-row ${report.id === selectedId ? 'selected' : ''}" data-id="${escapeHtml(report.id)}" aria-label="${escapeHtml(report.type)}, ${escapeHtml(report.severity)} severity, ${escapeHtml(report.location)}">${photo}<div class="incident-topline"><span class="incident-type"><i data-lucide="${iconFor(report.type)}"></i>${escapeHtml(report.type)}</span><span class="severity ${urgencyClass(report.severity)}">${escapeHtml(report.severity)}</span></div><div class="incident-location">${escapeHtml(report.title)} · ${escapeHtml(report.location)}</div><div class="incident-meta">${meta.map((item) => `<span title="${escapeHtml(item.title)}">${escapeHtml(item.label)}</span>`).join('<span aria-hidden="true">·</span>')}</div></button>`;
        }).join('');
      } else if (loadingIncidents) {
        queueContent = '<div class="empty-state"><strong>Loading incidents</strong><span>Connecting to the incident API.</span></div>';
      } else if (document.getElementById('apiStatus').dataset.state === 'error') {
        queueContent = '<div class="empty-state"><span class="empty-state-icon"><i data-lucide="radio"></i></span><strong>No incidents to show</strong><span>Refresh the feed to check for new reports.</span><button class="empty-state-action" data-retry-api><i data-lucide="refresh-cw"></i> Refresh feed</button></div>';
      } else if (reports.length) {
        queueContent = '<div class="empty-state"><strong>No matching incidents</strong><span>Try another priority filter.</span></div>';
      } else {
        queueContent = '<div class="empty-state"><span class="empty-state-icon"><i data-lucide="inbox"></i></span><strong>No incidents in feed</strong><span>New submissions will appear here when the backend returns them.</span><button class="empty-state-action" data-open-report><i data-lucide="plus"></i> Submit a report</button></div>';
      }
      list.innerHTML = queueContent;
      list.querySelectorAll('.incident-row').forEach((row) => row.addEventListener('click', () => selectIncident(row.dataset.id, true)));
      list.querySelectorAll('.incident-thumbnail').forEach((image) => {
        image.addEventListener('error', () => image.remove(), { once: true });
      });
      if (window.lucide) lucide.createIcons();
      updateCounts();
    }
    function updateCounts() {
      const apiState = document.getElementById('apiStatus').dataset.state;
      const dataAvailable = apiState === 'connected';
      const countText = (value) => dataAvailable ? String(value) : '—';
      const groups = incidentGroups();
      const openGroups = groups.filter((group) => group.some((report) => !['resolved', 'closed'].includes(report.status)));
      const urgent = openGroups.filter((group) => group.some((report) => ['critical', 'high'].includes(report.severity))).length;
      const open = openGroups.length;
      const duplicateAvailability = reports.some((report) => report.duplicate !== null);
      const allDuplicateDataAvailable = reports.every((report) => report.duplicate !== null);
      const duplicates = reports.filter((report) => report.duplicate === true).length;
      document.getElementById('openCount').textContent = countText(open);
      document.getElementById('urgentCount').textContent = countText(urgent);
      document.getElementById('duplicateCount').textContent = !dataAvailable || (reports.length && !allDuplicateDataAvailable) ? '—' : countText(duplicates);
      document.getElementById('queueCount').textContent = countText(groupedReports(visibleReports()).length);
      document.getElementById('sidebarCount').textContent = countText(groups.length);
      document.getElementById('reportCount').textContent = countText(groups.length);
      const mappedCount = reports.filter(isInMapRegion).length;
      const outsideMapCount = reports.filter(hasCoordinates).length - mappedCount;
      document.getElementById('mapStatus').textContent = apiState === 'error'
        ? 'Nepal · feed unavailable'
        : mappedCount
          ? `${mappedCount} reports in Nepal${outsideMapCount ? ` · ${outsideMapCount} outside map area` : ''}`
          : reports.length
            ? 'No reports in Nepal map area'
            : 'Nepal · no reports yet';
      document.getElementById('queueDataStatus').textContent = loadingIncidents ? 'Loading…' : apiState === 'error' ? 'Unavailable' : `${reports.length} report${reports.length === 1 ? '' : 's'} · ${groups.length} incident${groups.length === 1 ? '' : 's'}`;
      const hasReports = dataAvailable && reports.length > 0;
      document.getElementById('sortButton').disabled = !hasReports;
      ['locateButton', 'mapLayer'].forEach((id) => { document.getElementById(id).disabled = !mappedCount; });
      document.querySelector('[data-filter="duplicate"]').disabled = !dataAvailable || !duplicateAvailability;
      const hasSelection = reports.some((report) => report.id === selectedId);
      document.getElementById('zoomButton').disabled = !hasSelection;
      document.getElementById('copyCoordinatesButton').disabled = !hasSelection || !hasCoordinates(reports.find((report) => report.id === selectedId));
      const rescueCases = reports.filter((report) => report.peopleTrapped === 'yes' && !['rescued', 'not_required'].includes(report.rescueStatus)).length;
      document.getElementById('rescueNavCount').textContent = dataAvailable ? String(rescueCases).padStart(2, '0') : '—';
      renderRescueView(dataAvailable);
    }
    function renderRescueView(dataAvailable) {
      const rescuedCount = reports.filter((report) => report.rescueStatus === 'rescued').length;
      const trappedCount = reports.filter((report) => report.peopleTrapped === 'yes').length;
      const awaitingCount = reports.filter((report) => report.rescueStatus === 'awaiting' || (report.peopleTrapped === 'yes' && report.rescueStatus === null)).length;
      const countText = (count) => dataAvailable ? String(count).padStart(2, '0') : '—';
      document.getElementById('rescueTrappedCount').textContent = countText(trappedCount);
      document.getElementById('rescueConfirmedCount').textContent = countText(rescuedCount);
      document.getElementById('rescueAwaitingCount').textContent = countText(awaitingCount);
      document.getElementById('rescueRecordCount').textContent = dataAvailable ? String(reports.length).padStart(2, '0') : '—';

      const empty = document.getElementById('rescueEmpty');
      const tableBody = document.getElementById('rescueTableBody');
      tableBody.innerHTML = '';
      if (!dataAvailable || reports.length === 0) {
        empty.hidden = false;
        document.getElementById('rescueEmptyTitle').textContent = dataAvailable ? 'No incidents to track' : 'Rescue status not loaded';
        document.getElementById('rescueEmptyMessage').textContent = dataAvailable
          ? 'Rescue indicators will appear here when included in an incident report.'
          : 'Refresh the incident feed to retrieve rescue-related reports.';
        return;
      }

      empty.hidden = true;
      tableBody.innerHTML = reports.map((report) => {
        const outcome = rescueOutcome(report);
        const trappedLabel = report.peopleTrapped === 'yes' ? 'Yes' : report.peopleTrapped === 'no' ? 'No' : 'Unknown';
        return `<tr><td><button class="rescue-incident-link" data-rescue-incident="${escapeHtml(report.id)}">${escapeHtml(report.type)} · ${escapeHtml(report.id)}</button><small>${escapeHtml(report.title)}</small></td><td><span class="rescue-flag rescue-flag--${report.peopleTrapped}">${trappedLabel}</span></td><td><span class="rescue-outcome rescue-outcome--${outcome.state}">${outcome.label}</span></td><td>${escapeHtml(report.location)}</td><td>${escapeHtml(report.time)}</td></tr>`;
      }).join('');
      tableBody.querySelectorAll('[data-rescue-incident]').forEach((button) => button.addEventListener('click', () => {
        selectIncident(button.dataset.rescueIncident, false);
        document.querySelector('.nav-link[data-view="incidents"]').click();
      }));
    }
    function selectIncident(id, pan) {
      const report = reports.find((item) => item.id === id);
      if (!report) return;
      selectedId = id;
      document.getElementById('detailTitle').textContent = `${report.type} · ${report.id}`;
      const statusLabels = { new: 'New', under_review: 'Under review', verified: 'Verified', response_in_progress: 'Response in progress', resolved: 'Resolved' };
      const details = [report.description, report.priorityReason, `Assessment: ${getAnalysisLabel(report.analysisStatus)}`, `Status: ${statusLabels[report.status] || report.status}`];
      if (report.urgencyScore !== null) details.push(`Triage priority score: ${report.urgencyScore}/100`);
      if (report.peopleTrapped !== 'unknown') details.push(`People trapped: ${report.peopleTrapped}`);
      if (report.peopleAffected !== null) details.push(`People affected: ${report.peopleAffected}`);
      if (report.injuriesReported !== null) details.push(`Injuries reported: ${report.injuriesReported}`);
      if (report.roadBlocked !== 'unknown') details.push(`Road blocked: ${report.roadBlocked}`);
      if (report.vulnerableGroups.length) details.push(`Vulnerable groups: ${report.vulnerableGroups.join(', ')}`);
      if (report.needs.length) details.push(`Reported needs: ${report.needs.join(', ')}`);
      if (report.hazards.length) details.push(`Immediate hazards: ${report.hazards.join(', ')}`);
      if (report.analysisStatus === 'completed' && report.confidence !== null) details.push(`Model confidence estimate: ${report.confidence}%`);
      document.getElementById('detailDescription').textContent = details.filter(Boolean).join(' · ');
      document.getElementById('detailExplainer').textContent = report.analysisStatus === 'mock'
        ? 'Fallback assessment: no completed live model analysis was recorded. Severity and priority are preliminary; verify details manually.'
        : report.analysisStatus === 'completed'
          ? `AI-generated assessment${report.needsReview ? ' · human review recommended' : ''}. Priority is a triage score, not a probability. Confidence is the model’s estimate, not a calibrated guarantee.`
          : 'Assessment is not verified. Human review is recommended.';
      document.getElementById('detailEvidence').textContent = report.flags.length
        ? `Safety flags: ${report.flags.join(', ')}`
        : report.priorityReason ? `Why this priority: ${report.priorityReason}` : '';
      const corroboratingReports = groupedReports([report])[0].members;
      const reportDetails = document.getElementById('corroboratingReports');
      reportDetails.innerHTML = corroboratingReports.length > 1
        ? `<details class="corroborating-details"><summary>${corroboratingReports.length} independent reports grouped for this incident</summary><ul>${corroboratingReports.map((item) => `<li><strong>Report #${escapeHtml(item.id)}</strong> · ${escapeHtml(item.description)}</li>`).join('')}</ul></details>`
        : '';
      const statusSelect = document.getElementById('incidentStatus');
      statusSelect.innerHTML = '';
      const nextStatus = { new: 'under_review', under_review: 'verified', verified: 'response_in_progress', response_in_progress: 'resolved' }[report.status];
      const currentOption = document.createElement('option');
      currentOption.value = nextStatus || '';
      currentOption.textContent = nextStatus ? `Move to ${statusLabels[nextStatus]}` : statusLabels[report.status] || report.status;
      statusSelect.append(currentOption);
      statusSelect.disabled = !nextStatus;
      document.getElementById('updateStatusButton').disabled = !nextStatus;
      loadStatusHistory(report.id);
      const image = document.getElementById('detailImage');
      const photo = document.getElementById('detailPhoto');
      const imageUrl = getImageUrl(report.imageUrl);
      if (imageUrl) {
        image.src = imageUrl;
        photo.hidden = false;
        image.onerror = () => { photo.hidden = true; };
      } else {
        image.removeAttribute('src');
        photo.hidden = true;
      }
      renderQueue();
      if (pan && isInMapRegion(report)) {
        map.flyTo([report.lat, report.lng], Math.max(map.getZoom(), 14), { duration: .45 });
        markerById.get(id)?.openPopup();
      } else if (pan && hasCoordinates(report)) {
        notify('This report is outside the Nepal-focused map area.');
      }
    }
    async function loadStatusHistory(reportId) {
      const history = document.getElementById('statusHistory');
      history.textContent = 'Loading status history…';
      try {
        const response = await fetch(`${apiBaseUrl}/reports/${encodeURIComponent(reportId)}/status-history`, { headers: { Accept: 'application/json' } });
        if (!response.ok) throw new Error(`API returned HTTP ${response.status}`);
        const events = await response.json();
        history.textContent = events.length
          ? `Lifecycle changes: ${events.map((event) => `${event.previous_status.replaceAll('_', ' ')} → ${event.status.replaceAll('_', ' ')} by ${event.changed_by} at ${new Date(event.changed_at).toLocaleString()}`).join(' · ')}`
          : 'No lifecycle changes recorded yet.';
      } catch (error) {
        history.textContent = `Status history unavailable: ${error.message}`;
      }
    }
    async function updateSelectedStatus() {
      const report = reports.find((item) => item.id === selectedId);
      const status = document.getElementById('incidentStatus').value;
      if (!report || !status) return;
      const button = document.getElementById('updateStatusButton');
      button.disabled = true;
      try {
        const response = await fetch(`${apiBaseUrl}/reports/${encodeURIComponent(report.id)}/status`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify({
            status,
            changed_by: document.getElementById('statusActor').value.trim() || 'local responder'
          })
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.detail || `API returned HTTP ${response.status}`);
        notify(`Incident #${report.id} moved to ${status.replaceAll('_', ' ')}.`);
        await loadIncidents(false);
        await loadSituation();
      } catch (error) {
        notify(`Could not update incident status: ${error.message}`);
      } finally {
        const current = reports.find((item) => item.id === selectedId);
        button.disabled = !current || !({
          new: 'under_review',
          under_review: 'verified',
          verified: 'response_in_progress',
          response_in_progress: 'resolved'
        })[current.status];
      }
    }
    function refreshHeatLayer() {
      if (heatLayer) map.removeLayer(heatLayer);
      const mappedReports = reports.filter(isInMapRegion);
      if (document.getElementById('mapLayer').value !== 'heat' || !L.circle || !mappedReports.length) return;
      const severityColors = { critical: '#c84a3d', high: '#bd791c', medium: '#d3aa35', low: '#477895', unknown: '#7b837d' };
      heatLayer = L.layerGroup(mappedReports.map((report) => L.circle([report.lat, report.lng], { radius: report.severity === 'critical' ? 480 : report.severity === 'high' ? 350 : report.severity === 'medium' ? 220 : 140, color: severityColors[report.severity], fillColor: severityColors[report.severity], fillOpacity: .13, weight: 1, opacity: .35 }))).addTo(map);
    }
    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]));
    }
    function normalizeIncidents(payload) {
      const items = Array.isArray(payload) ? payload : payload?.incidents ?? payload?.data?.incidents ?? payload?.data;
      if (!Array.isArray(items)) throw new Error('Unexpected /incidents response. Expected an array or an object containing incidents.');
      return items.map((item, index) => {
        const latitudeValue = item.latitude ?? item.lat;
        const longitudeValue = item.longitude ?? item.lng ?? item.lon;
        const latitude = latitudeValue === null || latitudeValue === undefined || latitudeValue === '' ? null : Number(latitudeValue);
        const longitude = longitudeValue === null || longitudeValue === undefined || longitudeValue === '' ? null : Number(longitudeValue);
        const rawSeverity = item.severity ?? item.urgency ?? item.priority;
        const severityNumber = Number(rawSeverity);
        const severityText = String(rawSeverity ?? 'unknown').toLowerCase();
        const severity = Number.isFinite(severityNumber) && rawSeverity !== null && rawSeverity !== ''
          ? severityNumber >= 5 ? 'critical' : severityNumber >= 4 ? 'high' : severityNumber >= 3 ? 'medium' : severityNumber >= 1 ? 'low' : 'unknown'
          : ['critical', 'urgent', 'emergency'].includes(severityText) ? 'critical'
            : ['high', 'major'].includes(severityText) ? 'high'
              : ['medium', 'moderate'].includes(severityText) ? 'medium'
                : ['low', 'minor'].includes(severityText) ? 'low' : 'unknown';
        const rawDescription = item.description ?? item.summary ?? item.ai_summary ?? item.details ?? item.title;
        const description = typeof rawDescription === 'string' && rawDescription.trim() ? rawDescription : 'Incident details unavailable.';
        const rawType = String(item.incident_type ?? item.type ?? item.category ?? 'unknown');
        const type = rawType.replace(/[_-]+/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
        const locationValue = item.location ?? item.location_text ?? item.address ?? item.place_name;
        const location = String(locationValue ?? (Number.isFinite(latitude) && Number.isFinite(longitude) ? `${latitude.toFixed(5)}, ${longitude.toFixed(5)}` : 'Location unavailable'));
        const confidenceSource = item.confidence ?? item.confidence_score;
        const confidenceValue = confidenceSource === undefined || confidenceSource === null ? null : Number(confidenceSource);
        const receivedAtValue = item.received_at ?? item.created_at ?? item.reported_at ?? item.timestamp ?? '';
        const receivedAtText = String(receivedAtValue);
        const normalizedReceivedAt = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(receivedAtText) ? receivedAtText : `${receivedAtText}Z`;
        const receivedAt = Date.parse(normalizedReceivedAt);
        const ageMinutes = Number.isFinite(receivedAt) ? Math.max(0, Math.floor((Date.now() - receivedAt) / 60000)) : null;
        const time = ageMinutes === null ? 'time unavailable' : ageMinutes < 1 ? 'just now' : ageMinutes < 60 ? `${ageMinutes} min ago` : ageMinutes < 1440 ? `${Math.floor(ageMinutes / 60)} hr ago` : new Date(receivedAt).toLocaleDateString();
        return {
          id: String(item.incident_id ?? item.id ?? item.report_id ?? `API-${index + 1}`),
          typeKey: rawType.toLowerCase().replace(/[\s-]+/g, '_'),
          type,
          title: String(item.summary ?? item.ai_summary ?? item.title ?? description.split(/[.!?\n]/)[0].slice(0, 68) ?? 'Incident report'),
          location,
          lat: Number.isFinite(latitude) ? latitude : null,
          lng: Number.isFinite(longitude) ? longitude : null,
          severity,
          time,
          receivedAt: Number.isFinite(receivedAt) ? receivedAt : 0,
          confidence: confidenceValue === null || !Number.isFinite(confidenceValue) ? null : confidenceValue <= 1 ? Math.round(confidenceValue * 100) : Math.round(confidenceValue),
          urgencyScore: item.urgency_score === undefined || item.urgency_score === null ? null : Number(item.urgency_score),
          duplicate: item.duplicate === undefined && item.is_duplicate === undefined ? null : Boolean(item.duplicate ?? item.is_duplicate),
          duplicateOf: item.duplicate_of === null || item.duplicate_of === undefined ? null : String(item.duplicate_of),
          duplicateConfidence: item.duplicate_similarity === undefined || item.duplicate_similarity === null ? null : Number(item.duplicate_similarity),
          duplicateReason: item.duplicate_reason ?? null,
          imageUrl: item.image_url ?? null,
          analysisStatus: String(item.analysis_status ?? 'unknown'),
          status: String(item.status ?? 'new').toLowerCase(),
          statusUpdatedAt: item.status_updated_at ?? null,
          statusUpdatedBy: item.status_updated_by ?? null,
          priorityReason: item.priority_reason ?? null,
          peopleTrapped: normalizePeopleTrapped(item.people_trapped),
          peopleAffected: Number.isInteger(item.people_affected) ? item.people_affected : null,
          injuriesReported: Number.isInteger(item.injuries_reported) ? item.injuries_reported : null,
          hazards: Array.isArray(item.hazards) ? item.hazards.map(String) : [],
          vulnerableGroups: Array.isArray(item.vulnerable_groups) ? item.vulnerable_groups.map(String) : [],
          needs: Array.isArray(item.needs) ? item.needs.map(String) : [],
          flags: Array.isArray(item.flags) ? item.flags.map(String) : [],
          needsReview: item.needs_review === true,
          rescueStatus: normalizeRescueStatus(item),
          roadBlocked: item.road_blocked ?? 'unknown',
          supportingReports: Number(item.supporting_reports ?? 1),
          description,
          source: item.source ?? null
        };
      });
    }
    function refreshTypeOptions() {
      const select = document.getElementById('filterType');
      const selected = select.value;
      const types = [...new Set(reports.map((report) => [report.typeKey, report.type]))]
        .sort((left, right) => left[1].localeCompare(right[1]));
      select.innerHTML = '<option value="all">Any type</option>' + types.map(([value, label]) => `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`).join('');
      select.value = types.some(([value]) => value === selected) ? selected : 'all';
      activeType = select.value;
    }
    function renderSituation(data) {
      document.getElementById('situationUpdated').textContent = `Updated ${new Date(data.generated_at).toLocaleTimeString()} · nearby reports grouped within 3 km`;
      document.getElementById('situationTotals').textContent = `${data.total_reports} / ${data.distinct_incidents}`;
      document.getElementById('situationUrgent').textContent = `${data.critical_incidents} / ${data.high_priority_incidents}`;
      const typeEntries = Object.entries(data.type_counts || {}).slice(0, 5);
      document.getElementById('situationTypes').innerHTML = typeEntries.length
        ? typeEntries.map(([type, count]) => `<span>${escapeHtml(type.replace(/[_-]+/g, ' '))} <strong>${count}</strong></span>`).join('')
        : '<span>No incident types yet.</span>';
      const hotspots = data.hotspots || [];
      document.getElementById('situationHotspots').innerHTML = hotspots.length
        ? hotspots.slice(0, 5).map((hotspot) => `<button class="hotspot-link" type="button" data-hotspot-id="${escapeHtml(hotspot.incident_ids[0])}"><strong>${escapeHtml(hotspot.area)}</strong><span>${hotspot.incident_count} incidents · ${hotspot.report_count} reports</span></button>`).join('')
        : '<span>No nearby clusters found.</span>';
      document.querySelectorAll('[data-hotspot-id]').forEach((button) => button.addEventListener('click', () => {
        const id = String(button.dataset.hotspotId);
        activeFilter = 'all';
        activeType = 'all';
        activeSeverity = 'all';
        activeStatus = 'all';
        document.querySelectorAll('.filter-button').forEach((item) => item.classList.toggle('active', item.dataset.filter === 'all'));
        document.getElementById('filterType').value = 'all';
        document.getElementById('filterSeverity').value = 'all';
        document.getElementById('filterStatus').value = 'all';
        document.querySelector('.nav-link[data-view="incidents"]').click();
        selectIncident(id, true);
      }));
    }
    async function loadSituation() {
      const updated = document.getElementById('situationUpdated');
      try {
        const response = await fetch(`${apiBaseUrl}/situation`, { headers: { Accept: 'application/json' } });
        if (!response.ok) throw new Error(`API returned HTTP ${response.status}`);
        renderSituation(await response.json());
      } catch (error) {
        updated.textContent = `Situation summary unavailable: ${error.message}`;
        document.getElementById('situationTotals').textContent = '—';
        document.getElementById('situationUrgent').textContent = '—';
        document.getElementById('situationTypes').textContent = 'Could not load incident types.';
        document.getElementById('situationHotspots').textContent = 'Could not load nearby clusters.';
      }
    }
    async function generateBriefing() {
      const button = document.getElementById('briefingButton');
      const result = document.getElementById('briefingResult');
      button.disabled = true;
      result.textContent = 'Gemma is preparing a briefing from saved incident reports…';
      try {
        const response = await fetch(`${apiBaseUrl}/situation/briefing`, {
          method: 'POST',
          headers: { Accept: 'application/json' }
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || `API returned HTTP ${response.status}`);
        if (data.analysis_status !== 'completed') throw new Error(data.detail || 'No reports are available.');
        result.textContent = `${data.briefing} Based on ${data.based_on_incidents} distinct incidents · ${data.model}. ${data.key_points.join(' ')}`;
      } catch (error) {
        result.textContent = `Briefing unavailable: ${error.message}`;
      } finally {
        button.disabled = false;
      }
    }
    function setApiStatus(state, message) {
      const status = document.getElementById('apiStatus');
      status.dataset.state = state;
      document.getElementById('apiStatusText').textContent = state === 'error' ? 'Feed paused' : state === 'loading' ? 'Syncing' : 'Feed connected';
      document.getElementById('queueSource').textContent = state === 'connected' ? 'API' : state === 'loading' ? 'Syncing' : 'Feed paused';
    }
    async function loadIncidents(notifyOnError = true) {
      loadingIncidents = true;
      setApiStatus('loading', 'Syncing');
      renderQueue();
      try {
        const response = await fetch(`${apiBaseUrl}/incidents`, { headers: { Accept: 'application/json' } });
        if (!response.ok) throw new Error(`API returned HTTP ${response.status}`);
        const payload = await response.json();
        reports = normalizeIncidents(payload);
        refreshTypeOptions();
        selectedId = reports.some((report) => report.id === selectedId) ? selectedId : reports[0]?.id || null;
        loadingIncidents = false;
        setApiStatus('connected', 'API connected');
        renderMarkers();
        renderQueue();
        const bounds = L.latLngBounds(reports.filter(isInMapRegion).map((report) => [report.lat, report.lng]));
        if (bounds.isValid()) map.fitBounds(bounds.pad(.15), { maxZoom: 13 });
        if (selectedId) selectIncident(selectedId, false);
        else {
          document.getElementById('detailTitle').textContent = 'No incident selected';
          document.getElementById('detailDescription').textContent = 'Incident details will appear here when the API returns an incident.';
        }
      } catch (error) {
        loadingIncidents = false;
        setApiStatus('error', 'Feed paused');
        document.getElementById('queueSource').textContent = 'Feed paused';
        renderMarkers();
        renderQueue();
        if (notifyOnError) notify(`Could not refresh the incident feed: ${error.message}.`);
      }
    }
    function notify(message) {
      const toast = document.getElementById('toast');
      document.getElementById('toastMessage').textContent = message;
      toast.classList.add('show');
      window.setTimeout(() => toast.classList.remove('show'), 2800);
    }
    document.querySelectorAll('.filter-button').forEach((button) => button.addEventListener('click', () => {
      activeFilter = button.dataset.filter;
      document.querySelectorAll('.filter-button').forEach((item) => item.classList.toggle('active', item === button));
      renderQueue();
      renderMarkers();
    }));
    document.getElementById('filterType').addEventListener('change', (event) => {
      activeType = event.currentTarget.value;
      renderQueue();
      renderMarkers();
    });
    document.getElementById('filterSeverity').addEventListener('change', (event) => {
      activeSeverity = event.currentTarget.value;
      renderQueue();
      renderMarkers();
    });
    document.getElementById('filterStatus').addEventListener('change', (event) => {
      activeStatus = event.currentTarget.value;
      renderQueue();
      renderMarkers();
    });
    document.getElementById('sortButton').addEventListener('click', () => { urgencyFirst = !urgencyFirst; renderQueue(); });
    document.getElementById('locateButton').addEventListener('click', () => {
      const bounds = L.latLngBounds(reports.filter(isInMapRegion).map((report) => [report.lat, report.lng]));
      if (bounds.isValid()) map.fitBounds(bounds.pad(.15), { maxZoom: 13 });
    });
    document.getElementById('zoomButton').addEventListener('click', () => selectIncident(selectedId, true));
    document.getElementById('copyCoordinatesButton').addEventListener('click', async () => {
      const report = reports.find((item) => item.id === selectedId);
      if (!report || !hasCoordinates(report)) return;
      const coordinates = `${report.lat}, ${report.lng}`;
      try {
        await navigator.clipboard.writeText(coordinates);
        notify('Incident coordinates copied.');
      } catch {
        notify(coordinates);
      }
    });
    document.getElementById('mapLayer').addEventListener('change', refreshHeatLayer);
    document.getElementById('refreshButton').addEventListener('click', () => {
      loadIncidents();
      loadSituation();
    });
    document.getElementById('briefingButton').addEventListener('click', generateBriefing);
    document.getElementById('updateStatusButton').addEventListener('click', updateSelectedStatus);
    document.getElementById('notificationsButton').addEventListener('click', () => notify(reports.length ? `${reports.length} report${reports.length === 1 ? '' : 's'} in the local queue.` : 'No notifications yet. Reports submitted here will appear in the queue.'));
    function openReportDialog() {
      document.getElementById('reportDialog').showModal();
    }
    document.addEventListener('click', (event) => {
      if (event.target.closest('[data-open-report]')) openReportDialog();
      const mapAction = event.target.closest('[data-map-action]');
      if (mapAction?.dataset.mapAction === 'retry' || event.target.closest('[data-retry-api]')) loadIncidents();
      else if (mapAction?.dataset.mapAction === 'report') openReportDialog();
    });
    document.getElementById('closeDialog').addEventListener('click', () => document.getElementById('reportDialog').close());
    document.getElementById('cancelDialog').addEventListener('click', () => document.getElementById('reportDialog').close());
    const locationInput = document.getElementById('reportLocation');
    const latitudeInput = document.getElementById('reportLatitude');
    const longitudeInput = document.getElementById('reportLongitude');
    document.getElementById('useLocation').addEventListener('click', () => {
      const button = document.getElementById('useLocation');
      const label = document.getElementById('locationButtonLabel');
      if (!navigator.geolocation) {
        notify('This browser does not provide GPS location. Enter a location instead.');
        return;
      }
      button.disabled = true;
      label.textContent = 'Finding location…';
      navigator.geolocation.getCurrentPosition(({ coords }) => {
        latitudeInput.value = coords.latitude;
        longitudeInput.value = coords.longitude;
        button.disabled = false;
        label.textContent = 'GPS captured';
        notify('Phone location captured. Submit the report to place its map pin.');
      }, (error) => {
        const message = error.code === error.PERMISSION_DENIED
          ? 'Location permission was denied. Enter a location instead.'
          : error.code === error.TIMEOUT
            ? 'Location request timed out. Try again or enter a location.'
            : 'Phone location is unavailable. Enter a location instead.';
        button.disabled = false;
        label.textContent = 'Use my location';
        notify(message);
      }, { enableHighAccuracy: true, timeout: 12000, maximumAge: 30000 });
    });
    document.getElementById('reportImage').addEventListener('change', (event) => {
      const imageInput = event.currentTarget;
      const file = imageInput.files[0];
      const preview = document.getElementById('reportImagePreview');
      if (selectedPreviewUrl) URL.revokeObjectURL(selectedPreviewUrl);
      selectedPreviewUrl = null;
      preview.hidden = true;
      preview.removeAttribute('src');
      if (!file) return;
      if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
        imageInput.value = '';
        notify('Choose a JPEG, PNG, or WebP image.');
        return;
      }
      if (file.size > 5 * 1024 * 1024) {
        imageInput.value = '';
        notify('The image must be 5 MB or smaller.');
        return;
      }
      selectedPreviewUrl = URL.createObjectURL(file);
      preview.src = selectedPreviewUrl;
      preview.hidden = false;
    });
    document.getElementById('reportForm').addEventListener('submit', async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const text = document.getElementById('reportText').value;
      const latitude = Number(latitudeInput.value);
      const longitude = Number(longitudeInput.value);
      if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
        notify('Enter valid latitude and longitude coordinates.');
        return;
      }
      const submitButton = document.getElementById('submitReportButton');
      submitButton.disabled = true;
      submitButton.querySelector('span').textContent = 'Submitting…';
      try {
        const formData = new FormData();
        formData.append('description', locationInput.value.trim() ? `${text.trim()}\n\nReported location: ${locationInput.value.trim()}` : text.trim());
        formData.append('latitude', String(latitude));
        formData.append('longitude', String(longitude));
        const imageFile = document.getElementById('reportImage').files[0];
        if (imageFile) formData.append('image', imageFile);
        const response = await fetch(`${apiBaseUrl}/reports/upload`, {
          method: 'POST',
          headers: { Accept: 'application/json' },
          body: formData
        });
        if (!response.ok) {
          const error = await response.json().catch(() => null);
          const detail = Array.isArray(error?.detail) ? error.detail.map((item) => item.msg).join('; ') : error?.detail;
          throw new Error(detail || `API returned HTTP ${response.status}`);
        }
        const saved = await response.json();
        selectedId = saved.report?.id === undefined ? selectedId : String(saved.report.id);
        document.querySelector('.nav-link[data-view="incidents"]').click();
        document.querySelector('.filter-button[data-filter="all"]').click();
        form.reset();
        if (selectedPreviewUrl) URL.revokeObjectURL(selectedPreviewUrl);
        selectedPreviewUrl = null;
        document.getElementById('reportImagePreview').removeAttribute('src');
        document.getElementById('reportImagePreview').hidden = true;
        document.getElementById('locationButtonLabel').textContent = 'Use my location';
        document.getElementById('reportDialog').close();
        notify(`Report #${saved.report?.id ?? 'saved'} saved by the backend. Refreshing incident feed…`);
        await loadIncidents(false);
        await loadSituation();
      } catch (error) {
        notify(`Could not submit report: ${error.message}. Check API availability and CORS.`);
      } finally {
        submitButton.disabled = false;
        submitButton.querySelector('span').textContent = 'Submit report';
      }
    });
    function activateNavLink(activeLink) {
      document.querySelectorAll('.nav-link').forEach((link) => {
        const isActive = link === activeLink;
        link.classList.toggle('active', isActive);
        if (isActive) link.setAttribute('aria-current', 'page');
        else link.removeAttribute('aria-current');
      });
    }
    const viewContent = {
      overview: ['Situation overview', 'Community reports, organized by location and urgency.'],
      incidents: ['Incident queue', 'Review reports prioritized by reported severity and received time.'],
      rescues: ['Rescue operations', 'Track reported entrapment and confirmed rescue outcomes.'],
      map: ['Live incident map', 'Explore locations returned by the incident feed.']
    };
    document.querySelectorAll('.nav-link[data-view]').forEach((link) => link.addEventListener('click', (event) => {
      event.preventDefault();
      const view = link.dataset.view;
      document.querySelector('.main').dataset.view = view;
      document.getElementById('rescueView').hidden = view !== 'rescues';
      document.getElementById('viewTitle').textContent = viewContent[view][0];
      document.getElementById('breadcrumbTitle').textContent = viewContent[view][0];
      document.getElementById('viewSubtitle').textContent = viewContent[view][1];
      activateNavLink(link);
      if (view === 'map') requestAnimationFrame(() => map.invalidateSize());
    }));
    document.querySelectorAll('a[href="#reports"]').forEach((link) => link.addEventListener('click', (event) => {
      event.preventDefault();
      const navLink = link.closest('.nav-link');
      openReportDialog();
    }));
    renderMarkers();
    renderQueue();
    loadIncidents();
    loadSituation();
    if (window.lucide) lucide.createIcons();
    window.setTimeout(() => map.invalidateSize(), 150);
