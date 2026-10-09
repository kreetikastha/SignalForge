    const apiBaseUrl = 'http://127.0.0.1:8001';
    let reports = [];
    let loadingIncidents = true;
    let capturedCoordinates = null;
    const map = L.map('map', { zoomControl: false, scrollWheelZoom: false }).setView([30.2714, -97.7437], 12);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' }).addTo(map);
    L.control.zoom({ position: 'bottomright' }).addTo(map);
    const markerLayer = L.layerGroup().addTo(map);
    const markerById = new Map();
    let selectedId = reports[0]?.id || null;
    let activeFilter = 'all';
    let urgencyFirst = true;
    let heatLayer = null;
    const severityRank = { critical: 3, high: 2, medium: 1 };
    const iconFor = (type) => ({ 'Flooding': 'waves', 'Flash flooding': 'waves', 'Structure fire': 'flame', 'Road obstruction': 'construction', 'Medical emergency': 'heart-pulse', 'Power outage': 'zap', 'Water rescue': 'life-buoy' }[type] || 'triangle-alert');
    const urgencyClass = (value) => value === 'critical' ? 'critical' : value === 'high' ? 'high' : 'medium';
    const hasCoordinates = (report) => Number.isFinite(report.lat) && Number.isFinite(report.lng);
    const markerIcon = (report) => L.divIcon({ className: '', html: `<div class="map-pin ${urgencyClass(report.severity)}"><span>${report.severity === 'critical' ? '!' : report.severity === 'high' ? 'H' : 'M'}</span></div>`, iconSize: [28, 34], iconAnchor: [14, 30], popupAnchor: [0, -28] });

    function sortedReports() {
      return [...reports].sort((left, right) => {
        const urgency = severityRank[right.severity] - severityRank[left.severity];
        return urgencyFirst ? urgency || left.time.localeCompare(right.time) : left.time.localeCompare(right.time);
      });
    }
    function visibleReports() {
      const ordered = sortedReports();
      if (activeFilter === 'urgent') return ordered.filter((report) => report.severity === 'critical' || report.severity === 'high');
      if (activeFilter === 'duplicate') return ordered.filter((report) => report.duplicate);
      return ordered;
    }
    function renderMarkers() {
      const mappedReports = reports.filter(hasCoordinates);
      const mapEmpty = document.getElementById('mapEmpty');
      mapEmpty.hidden = mappedReports.length > 0;
      const apiFailed = document.getElementById('apiStatus').dataset.state === 'error';
      document.getElementById('mapEmptyTitle').textContent = apiFailed ? 'API unavailable' : reports.length ? 'No GPS pins yet' : 'Waiting for the first report';
      document.getElementById('mapEmptyDescription').textContent = apiFailed ? 'Refresh to retry loading incident locations.' : reports.length ? 'This response contains no GPS coordinates.' : 'Incident markers will appear here after intake.';
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
      list.innerHTML = shown.length ? shown.map((report) => `<button class="incident-row ${report.id === selectedId ? 'selected' : ''}" data-id="${escapeHtml(report.id)}" aria-label="${escapeHtml(report.type)}, ${escapeHtml(report.severity)} priority, ${escapeHtml(report.location)}"><div class="incident-topline"><span class="incident-type"><i data-lucide="${iconFor(report.type)}"></i>${escapeHtml(report.type)}</span><span class="severity ${urgencyClass(report.severity)}">${escapeHtml(report.severity)}</span></div><div class="incident-location">${escapeHtml(report.title)} · ${escapeHtml(report.location)}</div><div class="incident-meta"><span>${escapeHtml(report.time)}</span><span>·</span><span>${escapeHtml(report.source)}</span><span>·</span><span>${report.confidence}% confidence</span>${report.duplicate ? '<span class="duplicate-flag">· Possible duplicate</span>' : ''}${report.acknowledged ? '<span class="acknowledged-flag">· Acknowledged</span>' : ''}</div></button>`).join('') : loadingIncidents ? '<div class="empty-state"><strong>Loading incidents</strong><span>Connecting to the local incident API.</span></div>' : reports.length ? '<div class="empty-state"><strong>No matching incidents</strong><span>Try another priority filter.</span></div>' : '<div class="empty-state"><span class="empty-state-icon"><i data-lucide="inbox"></i></span><strong>No incidents returned</strong><span>Submitted incidents will appear here when available from the API.</span></div>';
      list.querySelectorAll('.incident-row').forEach((row) => row.addEventListener('click', () => selectIncident(row.dataset.id, true)));
      if (window.lucide) lucide.createIcons();
      updateCounts();
    }
    function updateCounts() {
      const urgent = reports.filter((report) => report.severity === 'critical' || report.severity === 'high').length;
      const duplicates = reports.filter((report) => report.duplicate).length;
      document.getElementById('openCount').textContent = String(reports.length).padStart(2, '0');
      document.getElementById('urgentCount').textContent = String(urgent).padStart(2, '0');
      document.getElementById('duplicateCount').textContent = String(duplicates).padStart(2, '0');
      document.getElementById('queueCount').textContent = String(reports.length).padStart(2, '0');
      document.getElementById('sidebarCount').textContent = String(reports.length).padStart(2, '0');
      document.getElementById('reportCount').textContent = String(reports.length).padStart(2, '0');
      const mappedCount = reports.filter(hasCoordinates).length;
      document.getElementById('mapStatus').textContent = mappedCount ? `${mappedCount} GPS location${mappedCount === 1 ? '' : 's'} · Greater Austin` : reports.length ? 'Reports awaiting GPS locations' : 'Greater Austin, Texas · Awaiting first report';
      document.getElementById('queueDataStatus').textContent = loadingIncidents ? 'Loading…' : `${reports.length} incident${reports.length === 1 ? '' : 's'}`;
      const hasReports = reports.length > 0;
      document.getElementById('sortButton').disabled = !hasReports;
      ['locateButton', 'mapLayer'].forEach((id) => { document.getElementById(id).disabled = !mappedCount; });
      const hasSelection = reports.some((report) => report.id === selectedId);
      document.getElementById('zoomButton').disabled = !hasSelection;
      document.getElementById('resolveButton').disabled = !hasSelection;
    }
    function selectIncident(id, pan) {
      const report = reports.find((item) => item.id === id);
      if (!report) return;
      selectedId = id;
      document.getElementById('detailTitle').textContent = `${report.type} · ${report.id}`;
      document.getElementById('detailDescription').textContent = `${report.description} ${report.confidence}% extraction confidence.`;
      const acknowledgeButton = document.getElementById('resolveButton');
      acknowledgeButton.classList.toggle('acknowledged', Boolean(report.acknowledged));
      acknowledgeButton.querySelector('span').textContent = report.acknowledged ? 'Reopen' : 'Acknowledge';
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
      heatLayer = L.layerGroup(mappedReports.map((report) => L.circle([report.lat, report.lng], { radius: report.severity === 'critical' ? 480 : report.severity === 'high' ? 350 : 220, color: report.severity === 'critical' ? '#c84a3d' : report.severity === 'high' ? '#bd791c' : '#4c9b6a', fillColor: report.severity === 'critical' ? '#c84a3d' : report.severity === 'high' ? '#bd791c' : '#4c9b6a', fillOpacity: .13, weight: 1, opacity: .35 }))).addTo(map);
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
        const rawSeverity = String(item.severity ?? item.urgency ?? item.priority ?? 'medium').toLowerCase();
        const severity = ['critical', 'urgent', 'emergency'].includes(rawSeverity) ? 'critical' : ['high', 'major'].includes(rawSeverity) ? 'high' : 'medium';
        const description = String(item.description ?? item.summary ?? item.details ?? item.title ?? 'Incident details unavailable.');
        const type = String(item.type ?? item.incident_type ?? item.category ?? 'Community report');
        const location = String(item.location ?? item.address ?? item.place_name ?? (Number.isFinite(latitude) && Number.isFinite(longitude) ? `${latitude.toFixed(5)}, ${longitude.toFixed(5)}` : 'Location awaiting verification'));
        const confidenceValue = Number(item.confidence ?? item.confidence_score ?? 0);
        return {
          id: String(item.id ?? item.incident_id ?? item.report_id ?? `API-${index + 1}`),
          type,
          title: String(item.title ?? item.summary ?? description.split(/[.!?\n]/)[0].slice(0, 68)),
          location,
          lat: Number.isFinite(latitude) ? latitude : null,
          lng: Number.isFinite(longitude) ? longitude : null,
          severity,
          time: String(item.time_ago ?? item.created_at ?? item.reported_at ?? item.timestamp ?? 'time unavailable'),
          source: String(item.source ?? item.channel ?? 'API report'),
          confidence: confidenceValue <= 1 && confidenceValue > 0 ? Math.round(confidenceValue * 100) : Math.round(confidenceValue),
          duplicate: Boolean(item.duplicate ?? item.is_duplicate ?? false),
          acknowledged: Boolean(item.acknowledged ?? false),
          description
        };
      });
    }
    function setApiStatus(state, message) {
      const status = document.getElementById('apiStatus');
      status.dataset.state = state;
      document.getElementById('apiStatusText').textContent = message;
      document.getElementById('queueSource').textContent = state === 'connected' ? 'API' : state === 'loading' ? 'Connecting' : 'API unavailable';
    }
    async function loadIncidents() {
      loadingIncidents = true;
      setApiStatus('loading', 'Connecting to API');
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
        setApiStatus('error', 'API connection failed');
        document.getElementById('queueSource').textContent = 'API error';
        renderMarkers();
        renderQueue();
        notify(`Could not load incidents: ${error.message}. Check that the API is running and allows this page origin (CORS).`);
      }
    }
    function inferIncident(text) {
      const normalized = text.toLowerCase();
      const categories = [
        { type: 'Structure fire', words: ['fire', 'smoke', 'burning', 'flame'] },
        { type: 'Flooding', words: ['flood', 'water rising', 'underwater', 'stranded in water'] },
        { type: 'Road obstruction', words: ['tree', 'blocked', 'debris', 'road', 'blocked road'] },
        { type: 'Medical emergency', words: ['injured', 'injury', 'hurt', 'medical', 'unconscious', 'trapped'] },
        { type: 'Power outage', words: ['power', 'electricity', 'outage', 'downed line'] },
        { type: 'Water rescue', words: ['rescue', 'stranded', 'creek', 'river'] }
      ];
      const category = categories.find((item) => item.words.some((word) => normalized.includes(word)));
      const type = category?.type || 'Community report';
      const criticalWords = ['trapped', 'injured', 'injury', 'unconscious', 'fire', 'rescue', 'stranded', 'life threatening'];
      const highWords = ['flood', 'water rising', 'blocked', 'smoke', 'tree', 'debris', 'urgent', 'danger'];
      const severity = criticalWords.some((word) => normalized.includes(word)) ? 'critical' : highWords.some((word) => normalized.includes(word)) ? 'high' : 'medium';
      const tokens = normalized.match(/[a-z]{4,}/g) || [];
      const isDuplicate = reports.some((report) => {
        const prior = `${report.type} ${report.title} ${report.description}`.toLowerCase().match(/[a-z]{4,}/g) || [];
        const overlap = tokens.filter((token) => prior.includes(token)).length;
        return overlap >= 3 && tokens.length > 0 && overlap / tokens.length >= .25;
      });
      return { type, severity, isDuplicate };
    }
    function notify(message) {
      const toast = document.getElementById('toast');
      document.getElementById('toastMessage').textContent = message;
      toast.classList.add('show');
      window.setTimeout(() => toast.classList.remove('show'), 2800);
    }
    function addReport(text, location, imageName, coordinates) {
      const inferred = inferIncident(text);
      const report = {
        id: `DL-${Math.floor(2500 + Math.random() * 400)}`,
        type: inferred.type,
        title: text.trim().split(/[.!?\n]/)[0].slice(0, 68) || 'New community report',
        location: location.trim() || 'Location awaiting verification',
        lat: coordinates?.latitude ?? null,
        lng: coordinates?.longitude ?? null,
        severity: inferred.severity,
        time: 'just now',
        source: imageName ? 'Image + text' : 'Citizen text',
        confidence: imageName ? 76 : 82,
        duplicate: inferred.isDuplicate,
        description: `${text.trim()}${imageName ? ` Attached image: ${imageName}.` : ''} Demo extraction only; verify details with responders.`
      };
      reports.unshift(report);
      selectedId = report.id;
      renderMarkers();
      renderQueue();
      selectIncident(report.id, Boolean(coordinates));
      document.getElementById('reportCount').textContent = String(reports.length).padStart(2, '0');
      notify(inferred.isDuplicate ? 'Report added. A possible duplicate was flagged for review.' : coordinates ? 'Report added with its GPS location.' : 'Report added without a GPS pin.');
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
    document.getElementById('resolveButton').addEventListener('click', () => {
      const report = reports.find((item) => item.id === selectedId);
      if (!report) return;
      report.acknowledged = !report.acknowledged;
      selectIncident(report.id, false);
      notify(report.acknowledged ? 'Incident acknowledged.' : 'Incident reopened.');
    });
    document.getElementById('mapLayer').addEventListener('change', refreshHeatLayer);
    document.getElementById('refreshButton').addEventListener('click', loadIncidents);
    document.getElementById('notificationsButton').addEventListener('click', () => notify(reports.length ? `${reports.length} report${reports.length === 1 ? '' : 's'} in the local queue.` : 'No notifications yet. Reports submitted here will appear in the queue.'));
    function openReportDialog() {
      document.getElementById('reportDialog').showModal();
    }
    document.getElementById('openReport').addEventListener('click', openReportDialog);
    document.addEventListener('click', (event) => {
      if (event.target.closest('[data-open-report]')) openReportDialog();
    });
    document.getElementById('closeDialog').addEventListener('click', () => document.getElementById('reportDialog').close());
    document.getElementById('cancelDialog').addEventListener('click', () => document.getElementById('reportDialog').close());
    document.getElementById('reportImage').addEventListener('change', (event) => {
      const file = event.target.files[0];
      document.getElementById('uploadName').textContent = file ? file.name : 'Attach an image';
    });
    const locationInput = document.getElementById('reportLocation');
    locationInput.addEventListener('input', () => { capturedCoordinates = null; });
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
        capturedCoordinates = { latitude: coords.latitude, longitude: coords.longitude };
        locationInput.value = `GPS: ${coords.latitude.toFixed(5)}, ${coords.longitude.toFixed(5)}`;
        button.disabled = false;
        label.textContent = 'Use my location';
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
    document.getElementById('reportForm').addEventListener('submit', (event) => {
      event.preventDefault();
      const text = document.getElementById('reportText').value;
      const location = document.getElementById('reportLocation').value;
      const image = document.getElementById('reportImage').files[0];
      if (image && image.size > 10 * 1024 * 1024) { notify('Image exceeds the 10 MB demo limit.'); return; }
      addReport(text, location, image?.name || '', capturedCoordinates);
      capturedCoordinates = null;
      event.currentTarget.reset();
      document.getElementById('uploadName').textContent = 'Attach an image';
      document.getElementById('reportDialog').close();
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
      incidents: ['Incident queue', 'Review reports prioritized by urgency and confidence.'],
      map: ['Live incident map', 'Explore reported locations across Greater Austin.']
    };
    document.querySelectorAll('.nav-link[data-view]').forEach((link) => link.addEventListener('click', (event) => {
      event.preventDefault();
      const view = link.dataset.view;
      document.querySelector('.main').dataset.view = view;
      document.getElementById('viewTitle').textContent = viewContent[view][0];
      document.getElementById('viewSubtitle').textContent = viewContent[view][1];
      activateNavLink(link);
      if (view === 'map') requestAnimationFrame(() => map.invalidateSize());
    }));
    document.querySelectorAll('a[href="#reports"]').forEach((link) => link.addEventListener('click', (event) => {
      event.preventDefault();
      const navLink = link.closest('.nav-link');
      if (navLink) activateNavLink(navLink);
      openReportDialog();
    }));
    renderMarkers();
    renderQueue();
    loadIncidents();
    if (window.lucide) lucide.createIcons();
    window.setTimeout(() => map.invalidateSize(), 150);
