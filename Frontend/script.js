    const apiBaseUrl = 'http://127.0.0.1:8001';
    let reports = [];
    let loadingIncidents = true;
    const map = L.map('map', { zoomControl: false, scrollWheelZoom: false }).setView([27.7172, 85.324], 10);
    const tileLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' }).addTo(map);
    L.control.zoom({ position: 'bottomright' }).addTo(map);
    const markerLayer = L.layerGroup().addTo(map);
    const markerById = new Map();
    let selectedId = reports[0]?.id || null;
    let activeFilter = 'all';
    let urgencyFirst = true;
    let heatLayer = null;
    const severityRank = { critical: 4, high: 3, medium: 2, low: 1, unknown: 0 };
    const iconFor = (type) => ({ flood: 'waves', landslide: 'mountain', fire: 'flame', earthquake: 'activity', road_blockage: 'construction', medical: 'heart-pulse', other: 'triangle-alert' }[String(type).toLowerCase().replace(/[\s-]+/g, '_')] || 'triangle-alert');
    const urgencyClass = (value) => ['critical', 'high', 'medium', 'low'].includes(value) ? value : 'unknown';
    const hasCoordinates = (report) => Number.isFinite(report.lat) && Number.isFinite(report.lng);
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

    function sortedReports() {
      return [...reports].sort((left, right) => {
        const urgency = severityRank[right.severity] - severityRank[left.severity];
        const timeOrder = (right.receivedAt ?? 0) - (left.receivedAt ?? 0);
        return urgencyFirst ? urgency || timeOrder : timeOrder;
      });
    }
    function visibleReports() {
      const ordered = sortedReports();
      if (activeFilter === 'urgent') return ordered.filter((report) => ['critical', 'high'].includes(report.severity));
      if (activeFilter === 'duplicate') return ordered.filter((report) => report.duplicate === true);
      return ordered;
    }
    function renderMarkers() {
      const mappedReports = reports.filter(hasCoordinates);
      const mapEmpty = document.getElementById('mapEmpty');
      mapEmpty.hidden = mappedReports.length > 0;
      const apiFailed = document.getElementById('apiStatus').dataset.state === 'error';
      document.getElementById('map').dataset.state = apiFailed ? 'error' : mappedReports.length ? 'ready' : loadingIncidents ? 'loading' : 'empty';
      document.getElementById('mapEmptyTitle').textContent = reports.length ? 'No coordinates returned' : 'No incidents yet';
      document.getElementById('mapEmptyDescription').textContent = apiFailed ? 'The Kathmandu Valley map is ready for new report locations.' : reports.length ? 'The incident feed has no usable latitude and longitude.' : 'New report locations will appear on the map.';
      document.getElementById('map').classList.toggle('map-has-data', mappedReports.length > 0);
      const mapAction = document.getElementById('mapEmptyAction');
      mapAction.dataset.mapAction = apiFailed ? 'retry' : 'report';
      mapAction.innerHTML = apiFailed ? '<i data-lucide="refresh-cw"></i> Refresh feed' : '<i data-lucide="plus"></i> Add report';
      if (window.lucide) lucide.createIcons();
      markerLayer.clearLayers();
      markerById.clear();
      mappedReports.forEach((report) => {
        const marker = L.marker([report.lat, report.lng], { icon: markerIcon(report) }).bindPopup(`<div class="popup-title">${escapeHtml(report.type)} · ${report.severity.toUpperCase()}</div><div class="popup-sub">${escapeHtml(report.location)}<br>${escapeHtml(report.title)}</div>`);
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
        queueContent = shown.map((report) => {
        const meta = [report.time, report.analysisStatus ? `Analysis: ${report.analysisStatus}` : null, report.confidence === null ? null : `${report.confidence}% confidence`, report.duplicate === true ? 'Possible duplicate' : null].filter(Boolean);
        return `<button class="incident-row ${report.id === selectedId ? 'selected' : ''}" data-id="${escapeHtml(report.id)}" aria-label="${escapeHtml(report.type)}, ${escapeHtml(report.severity)} severity, ${escapeHtml(report.location)}"><div class="incident-topline"><span class="incident-type"><i data-lucide="${iconFor(report.type)}"></i>${escapeHtml(report.type)}</span><span class="severity ${urgencyClass(report.severity)}">${escapeHtml(report.severity)}</span></div><div class="incident-location">${escapeHtml(report.title)} · ${escapeHtml(report.location)}</div><div class="incident-meta">${meta.map((item) => `<span>${escapeHtml(item)}</span>`).join('<span aria-hidden="true">·</span>')}</div></button>`;
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
      if (window.lucide) lucide.createIcons();
      updateCounts();
    }
    function updateCounts() {
      const apiState = document.getElementById('apiStatus').dataset.state;
      const dataAvailable = apiState === 'connected';
      const countText = (value) => dataAvailable ? String(value).padStart(2, '0') : '—';
      const urgent = reports.filter((report) => ['critical', 'high'].includes(report.severity)).length;
      const open = reports.filter((report) => !['resolved', 'closed'].includes(report.status)).length;
      const duplicateAvailability = reports.some((report) => report.duplicate !== null);
      const allDuplicateDataAvailable = reports.every((report) => report.duplicate !== null);
      const duplicates = reports.filter((report) => report.duplicate === true).length;
      document.getElementById('openCount').textContent = countText(open);
      document.getElementById('urgentCount').textContent = countText(urgent);
      document.getElementById('duplicateCount').textContent = !dataAvailable || (reports.length && !allDuplicateDataAvailable) ? '—' : countText(duplicates);
      document.getElementById('queueCount').textContent = countText(reports.length);
      document.getElementById('sidebarCount').textContent = countText(reports.length);
      document.getElementById('reportCount').textContent = countText(reports.length);
      const mappedCount = reports.filter(hasCoordinates).length;
      document.getElementById('mapStatus').textContent = apiState === 'error' ? 'Kathmandu Valley · no pins' : mappedCount ? `${mappedCount} of ${reports.length} incidents have coordinates` : reports.length ? 'No coordinates in the incident feed' : 'Kathmandu Valley · no pins';
      document.getElementById('queueDataStatus').textContent = loadingIncidents ? 'Loading…' : apiState === 'error' ? 'Unavailable' : `${reports.length} incident${reports.length === 1 ? '' : 's'}`;
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
      const details = [report.description, report.priorityReason, `Analysis: ${report.analysisStatus}`, `Status: ${report.status}`];
      if (report.peopleTrapped !== 'unknown') details.push(`People trapped: ${report.peopleTrapped}`);
      if (report.roadBlocked !== 'unknown') details.push(`Road blocked: ${report.roadBlocked}`);
      document.getElementById('detailDescription').textContent = details.filter(Boolean).join(' · ');
      renderQueue();
      if (pan && hasCoordinates(report)) {
        map.flyTo([report.lat, report.lng], Math.max(map.getZoom(), 14), { duration: .45 });
        markerById.get(id)?.openPopup();
      }
    }
    function refreshHeatLayer() {
      if (heatLayer) map.removeLayer(heatLayer);
      const mappedReports = reports.filter(hasCoordinates);
      if (document.getElementById('mapLayer').value !== 'heat' || !L.circle || !mappedReports.length) return;
      const severityColors = { critical: '#c84a3d', high: '#bd791c', medium: '#4c9b6a', low: '#477895', unknown: '#7b837d' };
      heatLayer = L.layerGroup(mappedReports.map((report) => L.circle([report.lat, report.lng], { radius: report.severity === 'critical' ? 480 : report.severity === 'high' ? 350 : report.severity === 'medium' ? 220 : 140, color: severityColors[report.severity], fillColor: severityColors[report.severity], fillOpacity: .13, weight: 1, opacity: .35 }))).addTo(map);
      markerLayer.bringToFront();
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
        const receivedAt = Date.parse(item.received_at ?? item.created_at ?? item.reported_at ?? item.timestamp ?? '');
        const ageMinutes = Number.isFinite(receivedAt) ? Math.max(0, Math.floor((Date.now() - receivedAt) / 60000)) : null;
        const time = ageMinutes === null ? 'time unavailable' : ageMinutes < 1 ? 'just now' : ageMinutes < 60 ? `${ageMinutes} min ago` : ageMinutes < 1440 ? `${Math.floor(ageMinutes / 60)} hr ago` : new Date(receivedAt).toLocaleDateString();
        return {
          id: String(item.incident_id ?? item.id ?? item.report_id ?? `API-${index + 1}`),
          type,
          title: String(item.summary ?? item.ai_summary ?? item.title ?? description.split(/[.!?\n]/)[0].slice(0, 68) ?? 'Incident report'),
          location,
          lat: Number.isFinite(latitude) ? latitude : null,
          lng: Number.isFinite(longitude) ? longitude : null,
          severity,
          time,
          receivedAt: Number.isFinite(receivedAt) ? receivedAt : 0,
          confidence: confidenceValue === null || !Number.isFinite(confidenceValue) ? null : confidenceValue <= 1 ? Math.round(confidenceValue * 100) : Math.round(confidenceValue),
          duplicate: item.duplicate === undefined && item.is_duplicate === undefined ? null : Boolean(item.duplicate ?? item.is_duplicate),
          analysisStatus: String(item.analysis_status ?? 'unknown'),
          status: String(item.status ?? 'new').toLowerCase(),
          priorityReason: item.priority_reason ?? null,
          peopleTrapped: normalizePeopleTrapped(item.people_trapped),
          rescueStatus: normalizeRescueStatus(item),
          roadBlocked: item.road_blocked ?? 'unknown',
          supportingReports: Number(item.supporting_reports ?? 1),
          description,
          source: item.source ?? null
        };
      });
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
        selectedId = reports.some((report) => report.id === selectedId) ? selectedId : reports[0]?.id || null;
        loadingIncidents = false;
        setApiStatus('connected', 'API connected');
        renderMarkers();
        renderQueue();
        const bounds = L.latLngBounds(reports.filter(hasCoordinates).map((report) => [report.lat, report.lng]));
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
    }));
    document.getElementById('sortButton').addEventListener('click', () => { urgencyFirst = !urgencyFirst; renderQueue(); });
    document.getElementById('locateButton').addEventListener('click', () => {
      const bounds = L.latLngBounds(reports.filter(hasCoordinates).map((report) => [report.lat, report.lng]));
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
    document.getElementById('refreshButton').addEventListener('click', loadIncidents);
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
    document.getElementById('reportForm').addEventListener('submit', async (event) => {
      event.preventDefault();
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
        const response = await fetch(`${apiBaseUrl}/reports`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify({
            description: locationInput.value.trim() ? `${text.trim()}\n\nReported location: ${locationInput.value.trim()}` : text.trim(),
            latitude,
            longitude
          })
        });
        if (!response.ok) {
          const error = await response.json().catch(() => null);
          const detail = Array.isArray(error?.detail) ? error.detail.map((item) => item.msg).join('; ') : error?.detail;
          throw new Error(detail || `API returned HTTP ${response.status}`);
        }
        event.currentTarget.reset();
        document.getElementById('locationButtonLabel').textContent = 'Use my location';
        document.getElementById('reportDialog').close();
        notify('Report submitted to the backend. Refreshing incidents…');
        await loadIncidents(false);
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
    if (window.lucide) lucide.createIcons();
    window.setTimeout(() => map.invalidateSize(), 150);
