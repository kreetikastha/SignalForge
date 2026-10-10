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
    let activeType = 'all';
    let activeSeverity = 'all';
    let activeStatus = 'all';
    let activeOperationFilter = 'all';
    let operationSearch = '';
    let urgencyFirst = true;
    let heatLayer = null;
    const mapRegion = { south: 26, north: 31, west: 79, east: 89 };
    const severityRank = { critical: 4, high: 3, medium: 2, low: 1, unknown: 0 };
    const operationLabels = {
      reported: 'Reported',
      verified: 'Verified',
      dispatched: 'Dispatched',
      rescue_active: 'Rescue active',
      completed: 'Completed',
      false_alarm: 'False alarm',
      no_rescue_required: 'No rescue required',
      unable_to_access: 'Unable to access'
    };
    const operationTransitions = {
      reported: ['verified', 'false_alarm', 'no_rescue_required'],
      verified: ['dispatched', 'false_alarm', 'no_rescue_required', 'unable_to_access'],
      dispatched: ['rescue_active', 'false_alarm', 'no_rescue_required', 'unable_to_access'],
      rescue_active: ['completed', 'unable_to_access']
    };
    let operationDialogIncidentId = null;
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
    function getCredibilityLabel(label) {
      return ({
        genuine: 'Credibility signal: plausible',
        uncertain: 'Credibility signal: uncertain',
        prank: 'Credibility signal: possible prank',
        spam: 'Credibility signal: possible spam',
        unassessed: 'Credibility signal: not assessed'
      })[label] || 'Credibility signal: not assessed';
    }
    function operationStatusLabel(status) {
      return operationLabels[status] || 'Reported';
    }
    function operationBadge(status) {
      const safeStatus = Object.hasOwn(operationLabels, status) ? status : 'reported';
      return `<span class="operation-status-badge operation-status--${safeStatus}">${operationStatusLabel(safeStatus)}</span>`;
    }
    function relativeAge(timestamp) {
      if (!timestamp) return 'Not updated';
      const parsed = Date.parse(timestamp);
      if (!Number.isFinite(parsed)) return 'Time unavailable';
      const minutes = Math.max(0, Math.floor((Date.now() - parsed) / 60000));
      if (minutes < 1) return 'Just now';
      if (minutes < 60) return `${minutes} min ago`;
      if (minutes < 1440) return `${Math.floor(minutes / 60)} hr ago`;
      return `${Math.floor(minutes / 1440)} day${Math.floor(minutes / 1440) === 1 ? '' : 's'} ago`;
    }
    function elapsedSinceDispatch(timestamp) {
      if (!timestamp) return 'Not dispatched';
      const parsed = Date.parse(timestamp);
      if (!Number.isFinite(parsed)) return 'Time unavailable';
      const minutes = Math.max(0, Math.floor((Date.now() - parsed) / 60000));
      if (minutes < 60) return `${minutes}m`;
      const hours = Math.floor(minutes / 60);
      return `${hours}h ${minutes % 60}m`;
    }
    const markerIcon = (report) => L.divIcon({ className: '', html: `<div class="map-pin ${urgencyClass(report.severity)}"><span>${({ critical: '!', high: 'H', medium: 'M', low: 'L', unknown: '?' })[urgencyClass(report.severity)]}</span></div>`, iconSize: [28, 34], iconAnchor: [14, 30], popupAnchor: [0, -28] });
    let selectedPreviewUrl = null;
    const createAnonymousReporterId = () => globalThis.crypto?.randomUUID?.()
      || `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
    function getAnonymousReporterId() {
      const storageKey = 'disasterlens-anonymous-reporter-id';
      try {
        const current = localStorage.getItem(storageKey);
        if (current) return current;
        const value = createAnonymousReporterId();
        localStorage.setItem(storageKey, value);
        return value;
      } catch {
        return `session-${createAnonymousReporterId()}`;
      }
    }
    const anonymousReporterId = getAnonymousReporterId();

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
        const marker = L.marker([report.lat, report.lng], { icon: markerIcon(report) }).bindPopup(`<div class="popup-title">${escapeHtml(report.type)} · ${report.severity.toUpperCase()}</div><div class="popup-sub">${operationStatusLabel(report.operationStatus)}${report.assignedTeam ? ` · ${escapeHtml(report.assignedTeam)}` : ''}<br>${escapeHtml(report.location)}<br>${escapeHtml(report.title)}${corroboration}</div>`);
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
        const rootId = report.duplicateOf ?? report.id;
        const groupMembers = reports.filter((member) => (member.duplicateOf ?? member.id) === rootId);
        const duplicateScore = Math.max(...groupMembers.map((member) => member.duplicateConfidence ?? 0));
        const credibilityCounts = new Map();
        groupMembers.forEach((member) => credibilityCounts.set(member.legitimacyLabel, (credibilityCounts.get(member.legitimacyLabel) || 0) + 1));
        const credibilitySummary = [...credibilityCounts.entries()]
          .map(([label, count]) => `${label.replace(/_/g, ' ')}${count > 1 ? ` ×${count}` : ''}`)
          .join(', ');
        const repeatReport = groupMembers.find((member) => member.repeatReporter);
        const meta = [
          { label: report.time, title: 'Time since this report was received.' },
          { label: getAnalysisLabel(report.analysisStatus), title: report.analysisStatus === 'mock' ? 'No completed live model analysis was recorded. Treat this preliminary assessment as unverified.' : 'Processing status of the report analysis.' },
          report.urgencyScore === null ? null : { label: `Priority ${report.urgencyScore}/100`, title: 'Triage score based on reported severity and needs; it is not a probability.' },
          report.analysisStatus === 'completed' && report.confidence !== null ? { label: `Model confidence ${report.confidence}%`, title: 'The model’s estimate of its own answer quality; this is not a calibrated probability.' } : null,
          { label: `Credibility signals: ${credibilitySummary || 'unassessed'}`, className: `trust-chip credibility-${groupMembers.some((member) => ['spam', 'prank'].includes(member.legitimacyLabel)) ? 'uncertain' : report.legitimacyLabel}`, title: `${groupMembers.map((member) => `#${member.id}: ${member.legitimacyReason || 'Automated assessment unavailable'}`).join(' · ')}. Advisory only; this never changes urgency.` },
          repeatReport ? { label: `Repeat reporter · ${repeatReport.reporterRepeatCount + 1} reports`, className: 'trust-chip repeat-reporter-flag', title: 'At least one anonymous reporter identifier in this group was used on an earlier report within the configured repeat window. This alone is not evidence of fraud.' } : null,
          groupMembers.length > 1 ? { label: `Group #${report.incidentGroupId} · ${groupMembers.length} reports${duplicateScore ? ` · ${Math.round(duplicateScore * 100)}% match` : ''}`, className: 'trust-chip incident-group-flag', title: report.duplicateReason || 'Reports grouped as possibly describing the same incident.' } : null
        ].filter(Boolean);
        const imageUrl = getImageUrl(report.imageUrl);
        const photo = imageUrl ? `<img class="incident-thumbnail" src="${escapeHtml(imageUrl)}" alt="Photo attached to report ${escapeHtml(report.id)}" loading="lazy">` : '';
        return `<button class="incident-row ${report.id === selectedId ? 'selected' : ''}" data-id="${escapeHtml(report.id)}" aria-label="${escapeHtml(report.type)}, ${escapeHtml(report.severity)} severity, ${operationStatusLabel(report.operationStatus)}, ${escapeHtml(report.location)}">${photo}<div class="incident-topline"><span class="incident-type"><i data-lucide="${iconFor(report.type)}"></i>${escapeHtml(report.type)}</span><span class="severity ${urgencyClass(report.severity)}">${escapeHtml(report.severity)}</span>${operationBadge(report.operationStatus)}</div><div class="incident-location">${escapeHtml(report.title)} · ${escapeHtml(report.location)}</div><div class="incident-meta">${meta.map((item) => `<span${item.className ? ` class="${escapeHtml(item.className)}"` : ''} title="${escapeHtml(item.title)}">${escapeHtml(item.label)}</span>`).join('<span aria-hidden="true">·</span>')}</div></button>`;
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
      const activeOperations = incidentGroups().filter((group) => {
        const operationStatus = group.find((report) => report.id === (group[0].duplicateOf ?? group[0].id))?.operationStatus ?? group[0].operationStatus;
        return ['dispatched', 'rescue_active'].includes(operationStatus);
      }).length;
      document.getElementById('rescueNavCount').textContent = dataAvailable ? String(activeOperations).padStart(2, '0') : '—';
      renderRescueView(dataAvailable);
    }
    function renderRescueView(dataAvailable) {
      const groups = groupedReports(reports).map(({ members, representative }) => ({
        ...representative,
        members
      }));
      const incidents = groups.sort((left, right) => {
        const priority = (right.urgencyScore ?? -1) - (left.urgencyScore ?? -1);
        return priority || (right.receivedAt ?? 0) - (left.receivedAt ?? 0);
      });
      const search = operationSearch.trim().toLowerCase();
      const visible = incidents.filter((incident) => {
        if (activeOperationFilter === 'rescue_active' && incident.operationStatus !== 'rescue_active') return false;
        if (activeOperationFilter === 'awaiting_dispatch' && incident.operationStatus !== 'verified') return false;
        if (activeOperationFilter === 'completed' && !['completed', 'false_alarm', 'no_rescue_required', 'unable_to_access'].includes(incident.operationStatus)) return false;
        if (!search) return true;
        return [
          incident.id,
          incident.type,
          incident.title,
          incident.location,
          incident.assignedTeam,
          ...incident.hazards
        ].some((value) => String(value ?? '').toLowerCase().includes(search));
      });
      const active = incidents.filter((incident) => ['dispatched', 'rescue_active'].includes(incident.operationStatus));
      document.getElementById('activeOperationRecords').textContent = dataAvailable ? String(active.length) : '—';
      const empty = document.getElementById('rescueEmpty');
      const tableBody = document.getElementById('rescueTableBody');
      const activeList = document.getElementById('activeOperationList');
      const activeEmpty = document.getElementById('activeOperationEmpty');
      tableBody.innerHTML = '';
      activeList.innerHTML = '';
      if (!dataAvailable || reports.length === 0) {
        empty.hidden = false;
        document.getElementById('rescueEmptyTitle').textContent = dataAvailable ? 'No incidents to manage' : 'Rescue status not loaded';
        document.getElementById('rescueEmptyMessage').textContent = dataAvailable
          ? 'New reports will appear here as operations to verify.'
          : 'Refresh the incident feed to retrieve rescue-related reports.';
        activeEmpty.hidden = false;
        activeEmpty.textContent = dataAvailable
          ? 'No teams are marked dispatched yet. Reported emergencies remain open until an operator records progress.'
          : 'Active operations are unavailable while the incident feed is disconnected.';
        return;
      }

      activeEmpty.hidden = active.length > 0;
      activeEmpty.textContent = 'No teams are marked dispatched yet. Reported emergencies remain open until an operator records progress.';
      activeList.innerHTML = active.map((incident) => {
        const team = incident.assignedTeam || 'Team not assigned';
        const elapsed = elapsedSinceDispatch(incident.dispatchedAt);
        const nextAction = incident.operationStatus === 'dispatched'
          ? 'Next: start rescue'
          : 'Next: confirm outcome';
        const trapped = incident.peopleTrapped === 'yes'
          ? (incident.peopleTrappedCount === null ? 'Trapped · count unknown' : `${incident.peopleTrappedCount} reported trapped`)
          : incident.peopleTrapped === 'no' ? 'No trapped people reported' : 'Trapped status unknown';
        return `<article class="active-operation-card"><div class="active-operation-card-top"><span class="active-operation-card-title">${escapeHtml(incident.type)} · #${escapeHtml(incident.id)}</span>${operationBadge(incident.operationStatus)}</div><div class="active-operation-card-location">${escapeHtml(incident.location)} · ${escapeHtml(trapped)}</div><div class="active-operation-card-meta"><span>${escapeHtml(team)} · ${escapeHtml(elapsed)} · Updated ${escapeHtml(relativeAge(incident.operationUpdatedAt || new Date(incident.receivedAt).toISOString()))} · ${escapeHtml(nextAction)}</span><button class="secondary-button operation-manage-button" type="button" data-manage-operation="${escapeHtml(incident.id)}">Manage operation</button></div></article>`;
      }).join('');

      empty.hidden = true;
      document.getElementById('rescueRecordCount').textContent = `${visible.length} / ${incidents.length}`;
      tableBody.innerHTML = visible.map((incident) => {
        const trapped = incident.peopleTrapped === 'yes'
          ? (incident.peopleTrappedCount === null ? 'Trapped · count unknown' : `${incident.peopleTrappedCount} trapped`)
          : incident.peopleTrapped === 'no' ? 'No trapped people reported' : 'Trapped status unknown';
        const activeTime = ['dispatched', 'rescue_active', 'completed', 'unable_to_access'].includes(incident.operationStatus)
          ? elapsedSinceDispatch(incident.dispatchedAt)
          : '—';
        const lastUpdated = incident.operationUpdatedAt || new Date(incident.receivedAt).toISOString();
        const priority = `<span class="severity ${urgencyClass(incident.severity)}">${escapeHtml(incident.severity)}</span><span class="rescue-trapped-note">${escapeHtml(trapped)}</span>`;
        return `<tr><td><button class="rescue-incident-link" data-rescue-incident="${escapeHtml(incident.id)}">${escapeHtml(incident.type)} · #${escapeHtml(incident.id)}</button><small>${escapeHtml(incident.title)} · ${escapeHtml(incident.location)}</small><div class="rescue-priority">${priority}</div></td><td>${operationBadge(incident.operationStatus)}</td><td>${escapeHtml(incident.assignedTeam || 'Not assigned')}</td><td>${escapeHtml(activeTime)}</td><td title="${escapeHtml(lastUpdated)}">${escapeHtml(relativeAge(lastUpdated))}</td><td><button class="secondary-button operation-manage-button" type="button" data-manage-operation="${escapeHtml(incident.id)}">Manage operation</button></td></tr>`;
      }).join('');
      tableBody.querySelectorAll('[data-rescue-incident]').forEach((button) => button.addEventListener('click', () => {
        selectIncident(button.dataset.rescueIncident, false);
        document.querySelector('.nav-link[data-view="incidents"]').click();
      }));
      document.querySelectorAll('[data-manage-operation]').forEach((button) => button.addEventListener('click', () => {
        openOperationDialog(button.dataset.manageOperation);
      }));
      if (!visible.length) {
        empty.hidden = false;
        document.getElementById('rescueEmptyTitle').textContent = incidents.length ? 'No matching operations' : 'No incidents to manage';
        document.getElementById('rescueEmptyMessage').textContent = incidents.length ? 'Try a different status filter or search term.' : 'New reports will appear here as operations to verify.';
      }
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
      const trustDetails = [
        `Credibility signal: ${getCredibilityLabel(report.legitimacyLabel)}.`,
        report.legitimacyReason || null,
        report.repeatReporter
          ? `Repeat reporter: ${report.reporterRepeatCount} earlier report(s) within the configured window.`
          : null,
        report.supportingReports > 1
          ? `Incident group #${report.incidentGroupId}: ${report.supportingReports} reports.`
          : null
      ].filter(Boolean);
      document.getElementById('detailEvidence').textContent = [
        report.flags.length ? `Safety flags: ${report.flags.join(', ')}` : null,
        report.priorityReason ? `Why this priority: ${report.priorityReason}` : null,
        ...trustDetails
      ].filter(Boolean).join(' · ');
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
    function renderOperationTimeline(detail) {
      const timeline = document.getElementById('operationTimeline');
      const events = Array.isArray(detail.history) ? detail.history : [];
      const latestByStatus = new Map();
      events.forEach((event) => {
        if (event.status) latestByStatus.set(event.status, event);
      });
      const completedStatuses = new Set(['reported', ...events.map((event) => event.status), detail.operation_status]);
      const timelineSteps = [
        { status: 'reported', label: 'Report received', time: detail.received_at },
        { status: 'verified', label: 'Incident verified' },
        { status: 'dispatched', label: 'Team dispatched', time: detail.dispatched_at },
        { status: 'rescue_active', label: 'Rescue in progress' },
        { status: 'completed', label: 'Rescue outcome confirmed' }
      ];
      const rows = timelineSteps.map((step) => {
        const event = latestByStatus.get(step.status);
        const timestamp = event?.changed_at || step.time;
        const actor = event?.changed_by ? ` · ${event.changed_by}` : '';
        const time = timestamp ? new Date(timestamp).toLocaleString() : 'Not recorded';
        return `<li class="${completedStatuses.has(step.status) ? 'is-complete' : ''}"><span>${escapeHtml(step.label)}${actor ? `<small>${escapeHtml(actor)}</small>` : ''}</span><time>${escapeHtml(time)}</time></li>`;
      });
      const outcomeStates = ['false_alarm', 'no_rescue_required', 'unable_to_access'];
      const outcomeEvent = [...events].reverse().find((event) => outcomeStates.includes(event.status));
      if (outcomeEvent) {
        rows.push(`<li class="is-complete"><span>${escapeHtml(operationStatusLabel(outcomeEvent.status))}<small>Recorded by ${escapeHtml(outcomeEvent.changed_by)}</small></span><time>${escapeHtml(new Date(outcomeEvent.changed_at).toLocaleString())}</time></li>`);
      }
      timeline.innerHTML = rows.join('');
    }
    async function openOperationDialog(incidentId) {
      const dialog = document.getElementById('operationDialog');
      const saveButton = document.getElementById('saveOperationButton');
      document.getElementById('operationFormMessage').dataset.terminal = 'false';
      saveButton.disabled = true;
      document.getElementById('operationFormMessage').textContent = 'Loading saved operation details…';
      try {
        const response = await fetch(`${apiBaseUrl}/incidents/${encodeURIComponent(incidentId)}/operation`, {
          headers: { Accept: 'application/json' }
        });
        const detail = await response.json();
        if (!response.ok) throw new Error(detail.detail || `API returned HTTP ${response.status}`);
        operationDialogIncidentId = String(detail.incident_id);
        const status = detail.operation_status || 'reported';
        const terminal = ['completed', 'false_alarm', 'no_rescue_required', 'unable_to_access'].includes(status);
        document.getElementById('operationDialogTitle').textContent = `${detail.incident_type.replaceAll('_', ' ')} · #${detail.incident_id}`;
        document.getElementById('operationDialogSubtitle').textContent = `${detail.location_text || 'Location not specified'} · ${detail.supporting_reports} report${detail.supporting_reports === 1 ? '' : 's'} in this incident`;
        document.getElementById('operationCurrentStatus').textContent = operationStatusLabel(status);
        document.getElementById('operationPriority').textContent = String(detail.severity || 'unknown').toUpperCase();
        document.getElementById('operationPeople').textContent = detail.people_trapped === 'yes'
          ? (Number.isInteger(detail.people_trapped_count) ? `${detail.people_trapped_count} reported trapped` : 'Reported · count unknown')
          : detail.people_trapped === 'no' ? 'None reported' : 'Unknown';
        document.getElementById('operationAiStatus').textContent = `Analysis ${getAnalysisLabel(detail.analysis_status || 'unknown')}`;
        document.getElementById('operationHazards').innerHTML = Array.isArray(detail.hazards) && detail.hazards.length
          ? detail.hazards.map((hazard) => `<span class="evidence-tag">${escapeHtml(hazard)}</span>`).join(' ')
          : 'No hazards reported.';
        renderOperationTimeline(detail);

        const statusSelect = document.getElementById('operationStatusInput');
        const selectableStatuses = [status, ...(operationTransitions[status] || [])];
        statusSelect.innerHTML = selectableStatuses.map((value) =>
          `<option value="${value}">${escapeHtml(operationStatusLabel(value))}</option>`
        ).join('');
        statusSelect.value = status;
        statusSelect.disabled = terminal;
        const teamInput = document.getElementById('operationAssignedTeam');
        teamInput.value = detail.assigned_team || '';
        teamInput.disabled = terminal;
        const actorInput = document.getElementById('operationActor');
        actorInput.value = '';
        actorInput.disabled = terminal;
        const countInput = document.getElementById('peopleRescuedInput');
        countInput.value = detail.people_rescued ?? '';
        countInput.disabled = terminal;
        document.getElementById('operationFormMessage').textContent = terminal
          ? `Outcome recorded: ${operationStatusLabel(status)}${detail.rescue_outcome === 'rescued' ? ` · ${detail.people_rescued} people confirmed rescued` : ''}. Terminal outcomes cannot be changed.`
          : 'AI analysis and incident review do not advance this rescue-operation workflow.';
        saveButton.disabled = terminal;
        document.getElementById('operationFormMessage').dataset.terminal = String(terminal);
        updateRescueCountField();
        if (!dialog.open) dialog.showModal();
      } catch (error) {
        notify(`Could not load rescue operation: ${error.message}`);
      } finally {
        if (!document.getElementById('operationFormMessage').dataset.terminal || document.getElementById('operationFormMessage').dataset.terminal === 'false') {
          saveButton.disabled = false;
        }
      }
    }
    function updateRescueCountField() {
      const completed = document.getElementById('operationStatusInput').value === 'completed';
      const field = document.getElementById('peopleRescuedField');
      const input = document.getElementById('peopleRescuedInput');
      field.hidden = !completed;
      input.required = completed;
      if (!completed) input.value = '';
      const message = document.getElementById('operationFormMessage');
      if (completed && message.dataset.terminal !== 'true') {
        message.textContent = 'Completion requires an explicitly confirmed rescued-person count.';
      }
    }
    async function saveOperationUpdate(event) {
      event.preventDefault();
      if (!operationDialogIncidentId) return;
      const status = document.getElementById('operationStatusInput').value;
      const assignedTeam = document.getElementById('operationAssignedTeam').value.trim();
      const saveButton = document.getElementById('saveOperationButton');
      const message = document.getElementById('operationFormMessage');
      if (['dispatched', 'rescue_active'].includes(status) && !assignedTeam) {
        message.textContent = 'Assign a response team before dispatching or activating a rescue.';
        document.getElementById('operationAssignedTeam').focus();
        return;
      }
      saveButton.disabled = true;
      message.textContent = 'Saving operation update…';
      const payload = {
        operation_status: status,
        assigned_team: assignedTeam || null,
        changed_by: document.getElementById('operationActor').value.trim() || 'local responder'
      };
      if (status === 'completed') payload.people_rescued = Number(document.getElementById('peopleRescuedInput').value);
      try {
        const response = await fetch(`${apiBaseUrl}/incidents/${encodeURIComponent(operationDialogIncidentId)}/operation`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify(payload)
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.detail || `API returned HTTP ${response.status}`);
        document.getElementById('operationDialog').close();
        notify(`Operation #${result.incident_id}: ${operationStatusLabel(result.operation_status)} saved.`);
        await loadIncidents(false);
        await loadSituation();
      } catch (error) {
        message.textContent = `Update failed: ${error.message}`;
        notify(`Could not update rescue operation: ${error.message}`);
      } finally {
        saveButton.disabled = false;
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
          incidentGroupId: String(item.incident_group_id ?? item.duplicate_of ?? item.incident_id ?? item.id ?? ''),
          reporterRepeatCount: Number.isInteger(item.reporter_repeat_count) ? item.reporter_repeat_count : 0,
          repeatReporter: item.repeat_reporter === true,
          legitimacyLabel: ['genuine', 'uncertain', 'prank', 'spam', 'unassessed'].includes(item.legitimacy_label)
            ? item.legitimacy_label
            : 'unassessed',
          legitimacyConfidence: item.legitimacy_confidence === undefined || item.legitimacy_confidence === null
            ? null
            : Number(item.legitimacy_confidence),
          legitimacyReason: item.legitimacy_reason ?? null,
          imageUrl: item.image_url ?? null,
          analysisStatus: String(item.analysis_status ?? 'unknown'),
          status: String(item.status ?? 'new').toLowerCase(),
          statusUpdatedAt: item.status_updated_at ?? null,
          statusUpdatedBy: item.status_updated_by ?? null,
          priorityReason: item.priority_reason ?? null,
          peopleTrapped: normalizePeopleTrapped(item.people_trapped),
          peopleAffected: Number.isInteger(item.people_affected) ? item.people_affected : null,
            peopleTrappedCount: Number.isInteger(item.people_trapped_count) ? item.people_trapped_count : null,
          injuriesReported: Number.isInteger(item.injuries_reported) ? item.injuries_reported : null,
          hazards: Array.isArray(item.hazards) ? item.hazards.map(String) : [],
          vulnerableGroups: Array.isArray(item.vulnerable_groups) ? item.vulnerable_groups.map(String) : [],
          needs: Array.isArray(item.needs) ? item.needs.map(String) : [],
          flags: Array.isArray(item.flags) ? item.flags.map(String) : [],
          needsReview: item.needs_review === true,
          operationStatus: Object.hasOwn(operationLabels, String(item.operation_status ?? 'reported').toLowerCase())
            ? String(item.operation_status ?? 'reported').toLowerCase()
            : 'reported',
          assignedTeam: item.assigned_team ?? null,
          dispatchedAt: item.dispatched_at ?? null,
          operationUpdatedAt: item.last_updated ?? item.operation_updated_at ?? null,
          rescueOutcome: item.rescue_outcome ?? null,
          peopleRescued: Number.isInteger(item.people_rescued) ? item.people_rescued : null,
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
      renderRescueMetrics(data.rescue_operations);
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
    function renderRescueMetrics(summary) {
      const metrics = summary || {};
      const metricValue = (key) => Number.isFinite(metrics[key]) ? String(metrics[key]) : '—';
      document.getElementById('activeOperationCount').textContent = metricValue('active_operations');
      document.getElementById('dispatchedTeamCount').textContent = metricValue('teams_dispatched');
      const trappedKnown = metrics.people_reported_trapped;
      const hasUnquantified = Number(metrics.trapped_count_unknown) > 0;
      document.getElementById('rescueTrappedCount').textContent = Number.isFinite(trappedKnown)
        ? trappedKnown === 0 && hasUnquantified ? '—' : String(trappedKnown)
        : '—';
      document.getElementById('rescueAwaitingCount').textContent = metricValue('awaiting_verification');
      document.getElementById('rescueConfirmedCount').textContent = metricValue('people_rescued_confirmed');
      document.getElementById('rescueTrappedNote').textContent = Number.isFinite(metrics.trapped_incidents)
        ? `${metrics.trapped_incidents} incidents · ${metrics.trapped_count_unknown || 0} without a count`
        : 'Reported counts only';
      document.getElementById('rescueConfirmedNote').textContent = Number.isFinite(metrics.confirmed_rescue_incidents)
        ? `${metrics.confirmed_rescue_incidents} incidents with confirmed outcomes`
        : 'Explicitly confirmed rescues only';
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
        renderRescueMetrics(null);
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
    document.querySelectorAll('[data-operation-filter]').forEach((button) => button.addEventListener('click', () => {
      activeOperationFilter = button.dataset.operationFilter;
      document.querySelectorAll('[data-operation-filter]').forEach((item) => item.classList.toggle('active', item === button));
      renderRescueView(document.getElementById('apiStatus').dataset.state === 'connected');
    }));
    document.getElementById('operationSearch').addEventListener('input', (event) => {
      operationSearch = event.currentTarget.value;
      renderRescueView(document.getElementById('apiStatus').dataset.state === 'connected');
    });
    document.getElementById('operationStatusInput').addEventListener('change', updateRescueCountField);
    document.getElementById('operationForm').addEventListener('submit', saveOperationUpdate);
    document.getElementById('closeOperationDialog').addEventListener('click', () => document.getElementById('operationDialog').close());
    document.getElementById('cancelOperationDialog').addEventListener('click', () => document.getElementById('operationDialog').close());
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
        formData.append('reporter_id', anonymousReporterId);
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
    window.setInterval(() => {
      loadIncidents(false);
      loadSituation();
    }, 30000);
    if (window.lucide) lucide.createIcons();
    window.setTimeout(() => map.invalidateSize(), 150);
