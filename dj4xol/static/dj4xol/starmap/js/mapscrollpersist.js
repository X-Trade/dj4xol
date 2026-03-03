// Global function for destination selection mode (called from map object onclick)
function persistStarmapScrollPosition() {
    try {
        var $starmap = $("#starmap");
        if ($starmap.length) {
            var storageKey = 'starmap:' + window.location.pathname;
            localStorage.setItem(storageKey + ':posX', $starmap.scrollLeft());
            localStorage.setItem(storageKey + ':posY', $starmap.scrollTop());
        }
    } catch (e) {}
}

function submitDestination(objectId, x, y, objectType) {
    if (window.playerTurnedIn) {
        return;
    }
    // Persist current map position before navigating
    persistStarmapScrollPosition();
    // Get current URL params and update with destination
    var params = new URLSearchParams(window.location.search);
    params.delete('mode');  // Exit destination mode
    // Clear all destination params first
    params.delete('dest_star');
    params.delete('dest_fleet');
    params.delete('dest_salvage');
    params.delete('dest_anomaly');
    params.delete('dest_x');
    params.delete('dest_y');
    // Set appropriate param based on object type
    if (objectType === 'fleet') {
        params.set('dest_fleet', objectId);
    } else if (objectType === 'salvage') {
        params.set('dest_salvage', objectId);
    } else if (objectType === 'anomaly') {
        params.set('dest_anomaly', objectId);
    } else {
        // Default to star for backwards compatibility
        params.set('dest_star', objectId);
    }
    window.location.search = params.toString();
}

// Submit coordinate-based destination (for empty space clicks)
function submitCoordinateDestination(x, y) {
    if (window.playerTurnedIn) {
        return;
    }
    // Persist current map position before navigating
    persistStarmapScrollPosition();
    var params = new URLSearchParams(window.location.search);
    params.delete('mode');  // Exit destination mode
    params.delete('dest_star');
    params.delete('dest_fleet');
    params.delete('dest_salvage');
    params.delete('dest_anomaly');
    params.set('dest_x', x);
    params.set('dest_y', y);
    window.location.search = params.toString();
}

$(document).ready(function() {
    var $starmap = $("#starmap");
    var $maparea = $("#maparea");
    var $sizer = $("#maparea-sizer");
    var $movementOverlay = $("#fleet-movement-overlay");

    // Prevent accidental link-drag when star names are visible; preserves click navigation.
    document.addEventListener('dragstart', function(ev) {
        var target = ev.target;
        if (target && target.closest && target.closest('.mapstar-name')) {
            ev.preventDefault();
        }
    });

    // Storage key prefix based on game URL (path only, no query params)
    var storageKey = 'starmap:' + window.location.pathname;

    // Get base dimensions from data attributes
    var baseWidth = parseInt($maparea.data('width')) || 600;
    var baseHeight = parseInt($maparea.data('height')) || 600;

    // Set maparea to base dimensions
    $maparea.css('width', baseWidth + 'px');
    $maparea.css('height', baseHeight + 'px');

    // Zoom state
    var zoomLevel = 1.0;
    var zoomMin = 0.5;
    var zoomMax = 3.0;
    var zoomStep = 0.25;

    // Restore zoom from localStorage
    var savedZoom = localStorage.getItem(storageKey + ':zoom');
    if (savedZoom) {
        zoomLevel = parseFloat(savedZoom);
    }
    applyZoom();

    // Locate toggle state (default on)
    var locateEnabled = localStorage.getItem(storageKey + ':locate') !== 'false';
    var $locateBtn = $('#starmap-locate');
    if (locateEnabled) {
        $locateBtn.addClass('active');
    }

    // Toggle locate on click
    $locateBtn.on('click', function(e) {
        e.preventDefault();
        locateEnabled = !locateEnabled;
        localStorage.setItem(storageKey + ':locate', locateEnabled);
        $locateBtn.toggleClass('active', locateEnabled);

        // When turning on, jump to current selection and show animation
        if (locateEnabled && urlX !== null && urlY !== null) {
            var borderOff = parseInt($maparea.data('border')) || 0;
            var targetX = (parseInt(urlX) * mapScale + borderOff) * zoomLevel;
            var targetY = (parseInt(urlY) * mapScale + borderOff) * zoomLevel;
            $starmap.scrollLeft(targetX - $starmap.width() / 2);
            $starmap.scrollTop(targetY - $starmap.height() / 2);
            showLocateAnimation(urlX, urlY);
        }
    });

    // Get coordinates for auto-locate: prefer selected object's actual position over URL params
    var urlParams = new URLSearchParams(window.location.search);
    var selX = $maparea.attr('data-sel-x');
    var selY = $maparea.attr('data-sel-y');
    var urlX = (selX !== undefined && selX !== null && selX !== '') ? selX : urlParams.get('x');
    var urlY = (selY !== undefined && selY !== null && selY !== '') ? selY : urlParams.get('y');
    var urlLocate = urlParams.get('locate');

    // Get border offset from maparea data attribute (in pixels, unscaled)
    var mapScale = 6;
    var borderOffset = parseInt($maparea.data('border')) || 0;
    var selectedFleetId = ($maparea.data('selected-fleet-id') || '').toString();
    var selectedObjectType = ($maparea.data('selected-object-type') || '').toString();
    var selectedObjectId = ($maparea.data('selected-object-id') || '').toString();
    var movementPaths = [];
    var wormholeLinks = [];
    var selectedPatrolCircles = [];
    var patrolPreviewCircle = null;
    var movementStateValues = ['off', 'selected', 'all'];
    var movementState = localStorage.getItem(storageKey + ':movementPaths') || 'selected';
    if (movementStateValues.indexOf(movementState) < 0) {
        movementState = 'selected';
    }
    var $movementBtn = $('#starmap-movement-paths');
    var $starNamesBtn = $('#starmap-star-names');

    (function loadMovementPaths() {
        var el = document.getElementById('movement-paths-json');
        if (!el) return;
        try {
            var parsed = JSON.parse(el.textContent || '[]');
            if (Array.isArray(parsed)) {
                movementPaths = parsed;
            }
        } catch (e) {
            movementPaths = [];
        }
    })();
    (function loadSelectedPatrolCircles() {
        var el = document.getElementById('selected-patrol-circles-json');
        if (!el) return;
        try {
            var parsed = JSON.parse(el.textContent || '[]');
            if (Array.isArray(parsed)) {
                selectedPatrolCircles = parsed;
            }
        } catch (e) {
            selectedPatrolCircles = [];
        }
    })();
    (function loadWormholeLinks() {
        var el = document.getElementById('wormhole-links-json');
        if (!el) return;
        try {
            var parsed = JSON.parse(el.textContent || '[]');
            if (Array.isArray(parsed)) {
                wormholeLinks = parsed;
            }
        } catch (e) {
            wormholeLinks = [];
        }
    })();

    function movementStateLabel(state) {
        if (state === 'off') return 'Off';
        if (state === 'all') return 'All';
        return 'Selected';
    }

    function movementStateIcon(state) {
        if (state === 'all') {
            return '' +
                '<svg class="movement-toggle-icon" viewBox="0 0 24 24" aria-hidden="true">' +
                '  <line class="movement-path" x1="4" y1="4" x2="20" y2="20"></line>' +
                '  <line class="movement-path" x1="4" y1="14" x2="20" y2="10"></line>' +
                '  <circle class="movement-node" cx="4" cy="4" r="2.2"></circle>' +
                '  <circle class="movement-node" cx="20" cy="20" r="2.2"></circle>' +
                '  <circle class="movement-node" cx="4" cy="14" r="2.2"></circle>' +
                '  <circle class="movement-node" cx="20" cy="10" r="2.2"></circle>' +
                '</svg>';
        }
        return '' +
            '<svg class="movement-toggle-icon" viewBox="0 0 24 24" aria-hidden="true">' +
            '  <line class="movement-path" x1="4" y1="20" x2="20" y2="4"></line>' +
            '  <circle class="movement-node" cx="4" cy="20" r="2.4"></circle>' +
            '  <circle class="movement-node" cx="20" cy="4" r="2.4"></circle>' +
            '</svg>';
    }

    function updateMovementButton() {
        if (!$movementBtn.length) {
            return;
        }
        $movementBtn.html(movementStateIcon(movementState));
        $movementBtn.toggleClass('active', movementState !== 'off');
        $movementBtn.removeClass('mode-off mode-selected mode-all');
        $movementBtn.addClass('mode-' + movementState);
        if (movementState === 'off') {
            $movementBtn.attr('title', 'Show Orders: Off');
        } else if (movementState === 'all') {
            $movementBtn.attr('title', 'Show Orders: All');
        } else {
            $movementBtn.attr('title', 'Show Orders: Selected');
        }
        $movementBtn.attr('aria-label', 'Show Orders: ' + movementStateLabel(movementState));
    }

    function appendPatrolCircle(overlay, ns, circleData, className) {
        if (!circleData) {
            return;
        }
        var centerX = (parseInt(circleData.center_x, 10) * mapScale) + borderOffset + 2.5;
        var centerY = (parseInt(circleData.center_y, 10) * mapScale) + borderOffset + 2.5;
        var radius = parseInt(circleData.radius, 10);
        if (!isFinite(centerX) || !isFinite(centerY) || !isFinite(radius) || radius < 0) {
            return;
        }

        var circle = document.createElementNS(ns, 'circle');
        circle.setAttribute('cx', centerX);
        circle.setAttribute('cy', centerY);
        circle.setAttribute('r', radius * mapScale);
        circle.setAttribute('class', className);
        overlay.appendChild(circle);
    }

    function drawMovementPaths() {
        if (!$movementOverlay.length) {
            return;
        }
        var overlay = $movementOverlay.get(0);
        if (!overlay) {
            return;
        }
        while (overlay.firstChild) {
            overlay.removeChild(overlay.firstChild);
        }
        if (movementState === 'off') {
            return;
        }

        var ns = 'http://www.w3.org/2000/svg';
        var cxOffset = 2.5;
        if (movementPaths.length) {
            for (var i = 0; i < movementPaths.length; i++) {
                var seg = movementPaths[i] || {};
                var fleetId = (seg.fleet_short_id || '').toString();
                var isSelected = !!selectedFleetId && fleetId === selectedFleetId;

                if (movementState === 'selected' && !isSelected) {
                    continue;
                }

                var x1 = (parseInt(seg.from_x, 10) * mapScale) + borderOffset + cxOffset;
                var y1 = (parseInt(seg.from_y, 10) * mapScale) + borderOffset + cxOffset;
                var x2 = (parseInt(seg.to_x, 10) * mapScale) + borderOffset + cxOffset;
                var y2 = (parseInt(seg.to_y, 10) * mapScale) + borderOffset + cxOffset;
                if (!isFinite(x1) || !isFinite(y1) || !isFinite(x2) || !isFinite(y2)) {
                    continue;
                }
                var line = document.createElementNS(ns, 'line');
                line.setAttribute('x1', x1);
                line.setAttribute('y1', y1);
                line.setAttribute('x2', x2);
                line.setAttribute('y2', y2);
                line.setAttribute('class', (
                    'fleet-movement-line ' + (isSelected ? 'fleet-movement-line-selected' : 'fleet-movement-line-other')
                ));
                overlay.appendChild(line);
            }
        }

        if (wormholeLinks.length) {
            for (var k = 0; k < wormholeLinks.length; k++) {
                var link = wormholeLinks[k] || {};
                var selectedVisible = (
                    selectedObjectType === 'anomaly' &&
                    selectedObjectId &&
                    (selectedObjectId === (link.a_short_id || '') || selectedObjectId === (link.b_short_id || ''))
                );
                if (movementState === 'selected' && !selectedVisible) {
                    continue;
                }
                var lx1 = (parseInt(link.ax, 10) * mapScale) + borderOffset + cxOffset;
                var ly1 = (parseInt(link.ay, 10) * mapScale) + borderOffset + cxOffset;
                var lx2 = (parseInt(link.bx, 10) * mapScale) + borderOffset + cxOffset;
                var ly2 = (parseInt(link.by, 10) * mapScale) + borderOffset + cxOffset;
                if (!isFinite(lx1) || !isFinite(ly1) || !isFinite(lx2) || !isFinite(ly2)) {
                    continue;
                }
                var wormholeLine = document.createElementNS(ns, 'line');
                wormholeLine.setAttribute('x1', lx1);
                wormholeLine.setAttribute('y1', ly1);
                wormholeLine.setAttribute('x2', lx2);
                wormholeLine.setAttribute('y2', ly2);
                wormholeLine.setAttribute('class', 'wormhole-link-line');
                overlay.appendChild(wormholeLine);
            }
        }

        if (selectedFleetId && selectedPatrolCircles.length) {
            for (var j = 0; j < selectedPatrolCircles.length; j++) {
                appendPatrolCircle(
                    overlay,
                    ns,
                    selectedPatrolCircles[j],
                    'fleet-patrol-radius fleet-patrol-radius-selected'
                );
            }
        }

        if (patrolPreviewCircle) {
            appendPatrolCircle(
                overlay,
                ns,
                patrolPreviewCircle,
                'fleet-patrol-radius fleet-patrol-radius-preview'
            );
        }
    }

    updateMovementButton();
    drawMovementPaths();

    $movementBtn.on('click', function(e) {
        e.preventDefault();
        var idx = movementStateValues.indexOf(movementState);
        if (idx < 0) {
            idx = 0;
        }
        movementState = movementStateValues[(idx + 1) % movementStateValues.length];
        localStorage.setItem(storageKey + ':movementPaths', movementState);
        updateMovementButton();
        drawMovementPaths();
    });

    window.addEventListener('dj4xol:patrolPreview', function(e) {
        var detail = (e && e.detail) || {};
        if (!detail.enabled) {
            patrolPreviewCircle = null;
            drawMovementPaths();
            return;
        }
        var centerX = parseInt(detail.center_x, 10);
        var centerY = parseInt(detail.center_y, 10);
        var radius = Math.max(0, parseInt(detail.radius, 10) || 0);
        if (!isFinite(centerX) || !isFinite(centerY)) {
            patrolPreviewCircle = null;
            drawMovementPaths();
            return;
        }
        patrolPreviewCircle = {
            center_x: centerX,
            center_y: centerY,
            radius: radius
        };
        drawMovementPaths();
    });

    var starNamesEnabled = localStorage.getItem(storageKey + ':starNames') === 'true';

    function updateStarNamesButton() {
        if (!$starNamesBtn.length) {
            return;
        }
        $starNamesBtn.toggleClass('active', starNamesEnabled);
        $starNamesBtn.attr('title', starNamesEnabled ? 'Star names: On' : 'Star names: Off');
        $starNamesBtn.attr('aria-label', starNamesEnabled ? 'Star names on' : 'Star names off');
        $maparea.toggleClass('show-star-names', starNamesEnabled);
    }

    updateStarNamesButton();

    $starNamesBtn.on('click', function(e) {
        e.preventDefault();
        starNamesEnabled = !starNamesEnabled;
        localStorage.setItem(storageKey + ':starNames', starNamesEnabled ? 'true' : 'false');
        updateStarNamesButton();
    });

    // Function to show locate animation at given map coordinates
    function showLocateAnimation(x, y) {
        var targetX = parseInt(x) * mapScale + borderOffset;
        var targetY = parseInt(y) * mapScale + borderOffset;

        // Create the ring element inside maparea (so it scales with zoom)
        var $ring = $('<div class="locate-ring"></div>');
        $ring.css({
            left: targetX + 'px',
            top: targetY + 'px'
        });
        $maparea.append($ring);

        // Remove after animation completes
        setTimeout(function() {
            $ring.remove();
        }, 1000);
    }

    // Check if in destination selection mode
    var destMode = $maparea.data('dest-mode') === true || $maparea.data('dest-mode') === 'true';

    var posX = localStorage.getItem(storageKey + ':posX');
    var posY = localStorage.getItem(storageKey + ':posY');
    var hasSavedPos = posX !== null && posY !== null;

    if ((locateEnabled && urlX !== null && urlY !== null && !destMode) || (urlLocate === '1' && urlX !== null && urlY !== null)) {
        // Center on selected coordinates (multiply by MAP_SCALE=6, add border offset)
        var targetX = (parseInt(urlX) * mapScale + borderOffset) * zoomLevel;
        var targetY = (parseInt(urlY) * mapScale + borderOffset) * zoomLevel;
        var centeredLeft = targetX - $starmap.width() / 2;
        var centeredTop = targetY - $starmap.height() / 2;
        var maxLeft = Math.max(0, (baseWidth * zoomLevel) - $starmap.width());
        var maxTop = Math.max(0, (baseHeight * zoomLevel) - $starmap.height());
        $starmap.scrollLeft(Math.max(0, Math.min(maxLeft, centeredLeft)));
        $starmap.scrollTop(Math.max(0, Math.min(maxTop, centeredTop)));

        // Show locate animation if requested
        if (urlLocate === '1') {
            showLocateAnimation(urlX, urlY);
        }
    } else if (hasSavedPos) {
        // Restore scroll position from localStorage
        $starmap.scrollLeft(posX);
        $starmap.scrollTop(posY);
    }

    function persistMapState() {
        localStorage.setItem(storageKey + ':posX', $starmap.scrollLeft());
        localStorage.setItem(storageKey + ':posY', $starmap.scrollTop());
        localStorage.setItem(storageKey + ':zoom', zoomLevel);
    }

    // Save scroll position and zoom before page unload
    $(window).bind('beforeunload', persistMapState);
    $starmap.on('scroll', persistMapState);

    // Click+drag scrolling
    var isDragging = false;
    var hasDragged = false;
    var startX, startY, scrollLeft, scrollTop;
    var dragSelectionLocked = false;

    function lockDragSelection() {
        if (dragSelectionLocked) {
            return;
        }
        dragSelectionLocked = true;
        document.body.classList.add('map-dragging');
    }

    function unlockDragSelection() {
        if (!dragSelectionLocked) {
            return;
        }
        dragSelectionLocked = false;
        document.body.classList.remove('map-dragging');
    }

    function shouldBlockMapDragStart(target) {
        var $target = $(target);
        if ($target.closest('.starmap-controls').length) {
            return true;
        }
        // Allow drag-start on visible star-name links so map panning still works.
        if ($target.closest('a').length && !$target.closest('.mapstar-name').length) {
            return true;
        }
        return false;
    }

    $starmap.on('mousedown', function(e) {
        if (shouldBlockMapDragStart(e.target)) return;
        isDragging = true;
        lockDragSelection();
        hasDragged = false;
        startX = e.pageX - $starmap.offset().left;
        startY = e.pageY - $starmap.offset().top;
        scrollLeft = $starmap.scrollLeft();
        scrollTop = $starmap.scrollTop();
    });

    $(document).on('mouseup', function() {
        isDragging = false;
        unlockDragSelection();
        // Reset hasDragged after a short delay so click handler can check it
        setTimeout(function() { hasDragged = false; }, 0);
    });

    $(window).on('blur', function() {
        isDragging = false;
        unlockDragSelection();
    });

    $(document).on('mousemove', function(e) {
        if (!isDragging) return;
        e.preventDefault();
        hasDragged = true;
        var x = e.pageX - $starmap.offset().left;
        var y = e.pageY - $starmap.offset().top;
        var walkX = (x - startX);
        var walkY = (y - startY);
        $starmap.scrollLeft(scrollLeft - walkX);
        $starmap.scrollTop(scrollTop - walkY);
    });

    var touchDragging = false;
    var touchStartX = 0;
    var touchStartY = 0;
    var touchScrollLeft = 0;
    var touchScrollTop = 0;
    var pinchStartDist = null;
    var pinchStartZoom = null;
    var gestureStartZoom = null;
    var touchPinching = false;
    var lastTouchPinchAt = 0;
    var pinchFramePending = false;
    var pinchFrameZoom = null;
    var pinchFrameX = 0;
    var pinchFrameY = 0;
    var isCoarsePointer = window.matchMedia &&
        window.matchMedia('(pointer: coarse)').matches;
    var isFinePointer = window.matchMedia &&
        window.matchMedia('(hover: hover) and (pointer: fine)').matches;
    var mobileDestinationTargeting = isCoarsePointer &&
        window.matchMedia &&
        window.matchMedia('(max-width: 900px)').matches;

    function getMobileTouchRadiusPx(objectType) {
        if (objectType === 'fleet') {
            return 22;
        }
        if (objectType === 'salvage') {
            return 20;
        }
        return 22; // stars
    }

    function findNearestSelectableMapObject(unscaledX, unscaledY) {
        if (!mobileDestinationTargeting) {
            return null;
        }

        var nearest = null;
        var nearestDistSq = Infinity;
        $maparea.find('[data-map-object="1"]').each(function() {
            var el = this;
            var objectType = el.getAttribute('data-object-type') || 'star';
            var radiusUnscaled = getMobileTouchRadiusPx(objectType) / zoomLevel;
            var maxDistSq = radiusUnscaled * radiusUnscaled;

            var left = parseFloat(el.style.left) || 0;
            var top = parseFloat(el.style.top) || 0;
            var width = el.offsetWidth || 5;
            var height = el.offsetHeight || 5;
            var centerX = left + (width / 2);
            var centerY = top + (height / 2);

            var dx = centerX - unscaledX;
            var dy = centerY - unscaledY;
            var distSq = dx * dx + dy * dy;
            if (distSq <= maxDistSq && distSq < nearestDistSq) {
                nearestDistSq = distSq;
                nearest = {
                    id: el.getAttribute('data-object-id'),
                    type: objectType,
                    x: parseInt(el.getAttribute('data-x'), 10),
                    y: parseInt(el.getAttribute('data-y'), 10)
                };
            }
        });
        return nearest;
    }

    function getTouchDistance(touches) {
        var dx = touches[0].clientX - touches[1].clientX;
        var dy = touches[0].clientY - touches[1].clientY;
        return Math.sqrt(dx * dx + dy * dy);
    }

    function getTouchMidpoint(touches) {
        return {
            x: (touches[0].clientX + touches[1].clientX) / 2,
            y: (touches[0].clientY + touches[1].clientY) / 2
        };
    }

    var starmapEl = $starmap.get(0);
    if (starmapEl) {
        // iOS Safari can still emit native gesture zoom while touching the map.
        // Block native multi-touch/gesture defaults inside starmap to keep
        // one authoritative zoom path and avoid pinch jitter.
        var blockNativeMultiTouch = function(e) {
            var target = e.target;
            if (!target || !starmapEl.contains(target)) {
                return;
            }
            if (e.touches && e.touches.length > 1) {
                e.preventDefault();
                return;
            }
            if (e.type.indexOf('gesture') === 0) {
                e.preventDefault();
            }
        };

        document.addEventListener(
            'touchmove',
            blockNativeMultiTouch,
            { passive: false }
        );
        document.addEventListener(
            'gesturestart',
            blockNativeMultiTouch,
            { passive: false }
        );
        document.addEventListener(
            'gesturechange',
            blockNativeMultiTouch,
            { passive: false }
        );
        document.addEventListener(
            'gestureend',
            blockNativeMultiTouch,
            { passive: false }
        );

        starmapEl.addEventListener('touchstart', function(e) {
            if (shouldBlockMapDragStart(e.target)) return;
            if (e.touches.length === 1) {
                touchDragging = true;
                lockDragSelection();
                pinchStartDist = null;
                pinchStartZoom = null;
                touchStartX = e.touches[0].clientX;
                touchStartY = e.touches[0].clientY;
                touchScrollLeft = $starmap.scrollLeft();
                touchScrollTop = $starmap.scrollTop();
            } else if (e.touches.length === 2) {
                e.preventDefault();
                touchDragging = false;
                touchPinching = true;
                pinchStartDist = getTouchDistance(e.touches);
                pinchStartZoom = zoomLevel;
            }
        }, { passive: false });

        starmapEl.addEventListener('touchmove', function(e) {
            if (e.touches.length === 1 && touchDragging) {
                e.preventDefault();
                var dx = e.touches[0].clientX - touchStartX;
                var dy = e.touches[0].clientY - touchStartY;
                $starmap.scrollLeft(touchScrollLeft - dx);
                $starmap.scrollTop(touchScrollTop - dy);
            } else if (e.touches.length === 2 && pinchStartDist && pinchStartZoom) {
                e.preventDefault();
                lastTouchPinchAt = Date.now();
                var currentDist = getTouchDistance(e.touches);
                var scale = currentDist / pinchStartDist;
                var newZoom = pinchStartZoom * scale;
                var midpoint = getTouchMidpoint(e.touches);
                var rect = starmapEl.getBoundingClientRect();
                pinchFrameZoom = newZoom;
                pinchFrameX = midpoint.x - rect.left;
                pinchFrameY = midpoint.y - rect.top;
                if (!pinchFramePending) {
                    pinchFramePending = true;
                    window.requestAnimationFrame(function() {
                        pinchFramePending = false;
                        if (pinchFrameZoom === null) {
                            return;
                        }
                        zoomTo(pinchFrameZoom, pinchFrameX, pinchFrameY);
                    });
                }
            }
        }, { passive: false });

        starmapEl.addEventListener('touchend', function(e) {
            touchDragging = false;
            if (!e.touches || e.touches.length === 0) {
                unlockDragSelection();
            }
            if (!e.touches || e.touches.length < 2) {
                touchPinching = false;
                lastTouchPinchAt = Date.now();
            }
            pinchStartDist = null;
            pinchStartZoom = null;
            pinchFrameZoom = null;
        }, { passive: false });

        starmapEl.addEventListener('touchcancel', function() {
            touchDragging = false;
            touchPinching = false;
            unlockDragSelection();
            lastTouchPinchAt = Date.now();
            pinchStartDist = null;
            pinchStartZoom = null;
            pinchFrameZoom = null;
        }, { passive: false });

        starmapEl.addEventListener('gesturestart', function(e) {
            e.preventDefault();
            if (isFinePointer) {
                gestureStartZoom = zoomLevel;
            }
        }, { passive: false });

        starmapEl.addEventListener('gesturechange', function(e) {
            e.preventDefault();
            if (isFinePointer) {
                if (gestureStartZoom === null || typeof e.scale !== 'number') {
                    return;
                }
                var rect = starmapEl.getBoundingClientRect();
                var viewportX = e.clientX - rect.left;
                var viewportY = e.clientY - rect.top;
                zoomTo(gestureStartZoom * e.scale, viewportX, viewportY);
            }
        }, { passive: false });

        starmapEl.addEventListener('gestureend', function(e) {
            e.preventDefault();
            if (isFinePointer) {
                gestureStartZoom = null;
            }
        }, { passive: false });
    }

    // Zoom functions
    function applyZoom() {
        $maparea.css('transform', 'scale(' + zoomLevel + ')');
        $maparea.css('transform-origin', '0 0');
        // Resize sizer to match visual size (controls scrollable area)
        $sizer.css('width', (baseWidth * zoomLevel) + 'px');
        $sizer.css('height', (baseHeight * zoomLevel) + 'px');
    }

    function zoomTo(newZoom, viewportX, viewportY) {
        // Clamp zoom level
        newZoom = Math.max(zoomMin, Math.min(zoomMax, newZoom));
        if (newZoom === zoomLevel) return;

        // Default to viewport center if no position provided
        if (viewportX === undefined) {
            viewportX = $starmap.width() / 2;
            viewportY = $starmap.height() / 2;
        }

        // Calculate point in content coordinates, then in unscaled coordinates
        var contentX = viewportX + $starmap.scrollLeft();
        var contentY = viewportY + $starmap.scrollTop();
        var unscaledX = contentX / zoomLevel;
        var unscaledY = contentY / zoomLevel;

        // Apply new zoom
        zoomLevel = newZoom;
        applyZoom();

        // Calculate new content position and adjust scroll to keep point under mouse
        var newContentX = unscaledX * zoomLevel;
        var newContentY = unscaledY * zoomLevel;
        var nextLeft = newContentX - viewportX;
        var nextTop = newContentY - viewportY;
        var maxLeft = Math.max(0, (baseWidth * zoomLevel) - $starmap.width());
        var maxTop = Math.max(0, (baseHeight * zoomLevel) - $starmap.height());
        $starmap.scrollLeft(Math.max(0, Math.min(maxLeft, nextLeft)));
        $starmap.scrollTop(Math.max(0, Math.min(maxTop, nextTop)));
        persistMapState();
    }

    // Zoom controls
    $('#starmap-zoom-in').on('click', function(e) {
        e.preventDefault();
        zoomTo(zoomLevel + zoomStep);
    });

    $('#starmap-zoom-out').on('click', function(e) {
        e.preventDefault();
        zoomTo(zoomLevel - zoomStep);
    });

    // Home button is a regular navigation link - no JS handler needed

    // Mousewheel zoom - zooms toward mouse position
    $starmap.on('wheel', function(e) {
        // Never wheel-zoom on coarse-pointer devices (phones/tablets).
        if (isCoarsePointer) {
            return;
        }
        if (touchPinching || (Date.now() - lastTouchPinchAt) < 300) {
            return;
        }
        var original = e.originalEvent;
        var isPinchWheel = !!original.ctrlKey;
        var likelyTrackpadPan = original.deltaMode === 0 &&
            (Math.abs(original.deltaY) < 40 || Math.abs(original.deltaX) > 0);

        // Allow normal scroll/pan for trackpad movement unless it's pinch-zoom.
        if (!isPinchWheel && likelyTrackpadPan) {
            return;
        }

        e.preventDefault();

        // Get mouse position relative to starmap viewport
        var offset = $starmap.offset();
        var viewportX = (original.pageX || e.pageX) - offset.left;
        var viewportY = (original.pageY || e.pageY) - offset.top;

        if (isPinchWheel) {
            // Continuous zoom for trackpad pinch wheel events.
            var scale = Math.exp(-original.deltaY * 0.002);
            zoomTo(zoomLevel * scale, viewportX, viewportY);
        } else {
            // Stepped zoom for traditional mouse wheel input.
            var delta = original.deltaY > 0 ? -zoomStep : zoomStep;
            zoomTo(zoomLevel + delta, viewportX, viewportY);
        }
    });

    // Destination mode: click on empty space to set coordinates
    if (destMode) {
        $maparea.on('click', function(e) {
            // Ignore clicks that were part of a drag-scroll
            if (hasDragged) return;
            // Let star links handle themselves (they call submitDestination via onclick)
            if ($(e.target).closest('a').length) return;

            // Calculate map coordinates from click position
            // Account for zoom level and border offset
            var offset = $maparea.offset();
            var clickX = e.pageX - offset.left;
            var clickY = e.pageY - offset.top;

            // Divide by zoom to get unscaled pixel position
            var unscaledX = clickX / zoomLevel;
            var unscaledY = clickY / zoomLevel;

            // On mobile, prefer nearby stars/fleets/salvage with a fixed
            // screen-space touch radius so selection remains usable at any zoom.
            var nearestObject = findNearestSelectableMapObject(unscaledX, unscaledY);
            if (nearestObject && nearestObject.id) {
                submitDestination(nearestObject.id, nearestObject.x, nearestObject.y, nearestObject.type);
                return;
            }

            // Reverse the coordinate transformation: pixel -> map coordinate
            // pixel = mapCoord * MAP_SCALE + borderOffset
            // mapCoord = (pixel - borderOffset) / MAP_SCALE
            var mapX = Math.round((unscaledX - borderOffset) / mapScale);
            var mapY = Math.round((unscaledY - borderOffset) / mapScale);

            submitCoordinateDestination(mapX, mapY);
        });
    }

    function ensureScrollFrame(el) {
        if (!el) return null;
        var parent = el.parentElement;
        if (!parent) return null;
        if (parent.classList.contains('panel-scroll-frame')) {
            return parent;
        }

        var frame = document.createElement('div');
        frame.className = 'panel-scroll-frame';
        if (el.classList.contains('panel-scrollable-list')) {
            frame.classList.add('panel-scroll-frame-list');
        }
        if (el.classList.contains('panel-scrollable-text')) {
            frame.classList.add('panel-scroll-frame-text');
        }
        parent.insertBefore(frame, el);
        frame.appendChild(el);
        return frame;
    }

    function updateCustomPanelScrollbar(el) {
        if (!el) return;
        var clientHeight = el.clientHeight || 0;
        var scrollHeight = el.scrollHeight || 0;
        if (clientHeight <= 0) return;
        var overlay = el.__customScrollbarOverlay;
        if (!overlay) return;
        var thumb = overlay.__thumbEl;
        if (!thumb) return;

        var thumbSize;
        var thumbTop;
        var thumbOpacity;
        var maxTop;
        var computed = window.getComputedStyle(el);
        var thumbScale = parseFloat(computed.getPropertyValue('--panel-scroll-thumb-scale'));
        var thumbMin = parseFloat(computed.getPropertyValue('--panel-scroll-thumb-min-size'));
        var thumbMax = parseFloat(computed.getPropertyValue('--panel-scroll-thumb-max-size'));
        var thumbMinRatio = parseFloat(computed.getPropertyValue('--panel-scroll-thumb-min-ratio'));
        var overlayTopOffset = parseFloat(computed.getPropertyValue('--panel-scroll-overlay-top-offset'));
        var trackInsetTop = parseFloat(computed.getPropertyValue('--panel-scroll-track-inset-top'));
        var trackInsetBottom = parseFloat(computed.getPropertyValue('--panel-scroll-track-inset-bottom'));
        if (!isFinite(thumbScale) || thumbScale <= 0) {
            thumbScale = 0.5;
        }
        if (!isFinite(thumbMin) || thumbMin <= 0) {
            thumbMin = 12;
        }
        if (!isFinite(thumbMax) || thumbMax <= 0) {
            thumbMax = Infinity;
        }
        if (!isFinite(thumbMinRatio) || thumbMinRatio < 0) {
            thumbMinRatio = 0;
        }
        if (!isFinite(overlayTopOffset)) {
            overlayTopOffset = 0;
        }
        if (!isFinite(trackInsetTop) || trackInsetTop < 0) {
            trackInsetTop = 0;
        }
        if (!isFinite(trackInsetBottom) || trackInsetBottom < 0) {
            trackInsetBottom = 0;
        }
        if (overlayTopOffset === 0 && document.body.classList.contains('lcars')) {
            overlayTopOffset = -3;
        }

        var track = overlay.__trackEl;
        var usableHeight = Math.max(0, clientHeight - trackInsetTop - trackInsetBottom);
        if (track) {
            track.style.top = trackInsetTop + 'px';
            track.style.bottom = trackInsetBottom + 'px';
            track.style.left = '0px';
            track.style.right = '0px';
        }

        if (scrollHeight <= clientHeight + 1) {
            thumbSize = Math.max(20, Math.min(usableHeight, Math.round(usableHeight * 0.35)));
            thumbSize = Math.max(thumbMin, Math.round(thumbSize * thumbScale));
            maxTop = Math.max(0, usableHeight - thumbSize);
            thumbTop = Math.round(maxTop / 2);
            thumbOpacity = 0;
        } else {
            var ratio = clientHeight / scrollHeight;
            thumbSize = Math.max(20, Math.round(usableHeight * ratio));
            thumbSize = Math.max(thumbMin, Math.round(thumbSize * thumbScale));
            maxTop = Math.max(0, usableHeight - thumbSize);
            thumbTop = Math.round((el.scrollTop / (scrollHeight - clientHeight)) * maxTop);
            thumbOpacity = 1;
        }

        var cssThumbMin = parseFloat(window.getComputedStyle(thumb).minHeight);
        if (!isFinite(cssThumbMin) || cssThumbMin < 0) {
            cssThumbMin = 0;
        }
        var ratioThumbMin = Math.round(usableHeight * thumbMinRatio);
        var enforcedMin = Math.max(thumbMin, cssThumbMin, ratioThumbMin);
        thumbSize = Math.max(enforcedMin, thumbSize);
        thumbSize = Math.min(thumbSize, thumbMax);
        thumbSize = Math.min(thumbSize, usableHeight);

        maxTop = Math.max(0, usableHeight - thumbSize);
        thumbTop = trackInsetTop + Math.max(0, Math.min(thumbTop, maxTop));

        overlay.style.top = overlayTopOffset + 'px';
        overlay.style.right = '0px';
        var overlayHeight = clientHeight;
        if (overlayTopOffset < 0) {
            overlayHeight = Math.max(0, clientHeight + overlayTopOffset);
        }
        overlay.style.height = overlayHeight + 'px';
        thumb.style.height = thumbSize + 'px';
        thumb.style.transform = 'translateY(' + thumbTop + 'px)';
        thumb.style.opacity = String(thumbOpacity);
        el.__customScrollbarMetrics = {
            clientHeight: clientHeight,
            scrollHeight: scrollHeight,
            thumbSize: thumbSize,
            maxTop: maxTop,
            trackInsetTop: trackInsetTop
        };
    }

    function ensureCustomScrollbarOverlay(el) {
        if (!el || el.__customScrollbarOverlay) {
            return el ? el.__customScrollbarOverlay : null;
        }
        var parent = el.parentElement;
        if (!parent) {
            return null;
        }
        var computedPos = window.getComputedStyle(parent).position;
        if (!computedPos || computedPos === 'static') {
            parent.style.position = 'relative';
        }
        var overlay = document.createElement('span');
        overlay.className = 'panel-scrollbar-overlay';
        var track = document.createElement('span');
        track.className = 'panel-scrollbar-track';
        var thumb = document.createElement('span');
        thumb.className = 'panel-scrollbar-thumb';
        overlay.appendChild(track);
        overlay.appendChild(thumb);
        parent.appendChild(overlay);
        el.__customScrollbarOverlay = overlay;
        overlay.__thumbEl = thumb;
        overlay.__trackEl = track;

        // Click track to jump near click position.
        overlay.addEventListener('pointerdown', function(ev) {
            if (ev.target === thumb) {
                return;
            }
            var metrics = el.__customScrollbarMetrics;
            if (!metrics || metrics.scrollHeight <= metrics.clientHeight || metrics.maxTop <= 0) {
                return;
            }
            var rect = overlay.getBoundingClientRect();
            var y = ev.clientY - rect.top - (metrics.trackInsetTop || 0);
            var targetTop = y - (metrics.thumbSize / 2);
            targetTop = Math.max(0, Math.min(targetTop, metrics.maxTop));
            el.scrollTop = (targetTop / metrics.maxTop) * (metrics.scrollHeight - metrics.clientHeight);
            updateCustomPanelScrollbar(el);
        });

        // Drag thumb to scroll (desktop + mobile pointer events).
        thumb.addEventListener('pointerdown', function(ev) {
            ev.preventDefault();
            var startY = ev.clientY;
            var startScrollTop = el.scrollTop;
            var metrics = el.__customScrollbarMetrics;
            if (!metrics || metrics.maxTop <= 0 || metrics.scrollHeight <= metrics.clientHeight) {
                return;
            }
            var pxToScroll = (metrics.scrollHeight - metrics.clientHeight) / metrics.maxTop;
            try {
                thumb.setPointerCapture(ev.pointerId);
            } catch (err) {}

            function onMove(moveEv) {
                var dy = moveEv.clientY - startY;
                el.scrollTop = startScrollTop + (dy * pxToScroll);
                updateCustomPanelScrollbar(el);
            }

            function onEnd(endEv) {
                document.removeEventListener('pointermove', onMove);
                document.removeEventListener('pointerup', onEnd);
                document.removeEventListener('pointercancel', onEnd);
                try {
                    thumb.releasePointerCapture(endEv.pointerId);
                } catch (err) {}
            }

            document.addEventListener('pointermove', onMove);
            document.addEventListener('pointerup', onEnd);
            document.addEventListener('pointercancel', onEnd);
        });

        // Wheel over overlay should still scroll content.
        overlay.addEventListener('wheel', function(ev) {
            ev.preventDefault();
            el.scrollTop += ev.deltaY;
            updateCustomPanelScrollbar(el);
        }, { passive: false });
        return overlay;
    }

    function refreshCustomPanelScrollbars() {
        if (!document.body.classList.contains('lcars') &&
            !document.body.classList.contains('win95')) {
            return;
        }
        var scrollEls = document.querySelectorAll('.panel-scrollable-list, .panel-scrollable-text');
        for (var i = 0; i < scrollEls.length; i += 1) {
            var el = scrollEls[i];
            ensureScrollFrame(el);
            if (!el.__customScrollbarBound) {
                el.__customScrollbarBound = true;
                ensureCustomScrollbarOverlay(el);
                el.addEventListener('scroll', function(ev) {
                    updateCustomPanelScrollbar(ev.currentTarget);
                });
            }
            ensureCustomScrollbarOverlay(el);
            updateCustomPanelScrollbar(el);
        }
    }

    // Messages scroll persistence
    var $messages = $('#messages');
    if ($messages.length) {
        var messagesKey = storageKey + ':messages';
        var currentYear = $messages.data('year');
        var savedYear = localStorage.getItem(messagesKey + ':year');
        var savedScroll = localStorage.getItem(messagesKey + ':scroll');

        // Restore scroll position only if same year
        if (savedYear && parseInt(savedYear) === currentYear && savedScroll) {
            $messages.scrollTop(parseInt(savedScroll));
        }

        // Save scroll position on scroll
        $messages.on('scroll', function() {
            localStorage.setItem(messagesKey + ':scroll', $messages.scrollTop());
            localStorage.setItem(messagesKey + ':year', currentYear);
        });
    }

    // Collapsible sections (detail subsections)
    var collapseKey = storageKey + ':collapse';

    // Restore collapsed state
    $('.collapsible-section').each(function() {
        var $section = $(this);
        var sectionName = $section.data('section');
        var isCollapsed = localStorage.getItem(collapseKey + ':' + sectionName) === 'true';
        if (isCollapsed) {
            $section.addClass('collapsed');
            $section.find('.collapse-toggle').text('+');
        }
    });

    // Toggle on header click
    $('.collapsible-header').on('click', function() {
        var $section = $(this).closest('.collapsible-section');
        var sectionName = $section.data('section');
        var $toggle = $section.find('.collapse-toggle');

        $section.toggleClass('collapsed');
        var isCollapsed = $section.hasClass('collapsed');
        $toggle.text(isCollapsed ? '+' : '−');
        localStorage.setItem(collapseKey + ':' + sectionName, isCollapsed);
        setTimeout(refreshCustomPanelScrollbars, 0);
    });

    // Panel collapse (main panels like Starmap, Messages, Detail, Orders)
    var panelKey = storageKey + ':panel';

    // Restore panel state (without animation)
    $('.panel').each(function() {
        var $panel = $(this);
        var panelName = $panel.data('panel');
        var isOpen = localStorage.getItem(panelKey + ':' + panelName);
        // Default to open if not set
        if (isOpen === 'false') {
            $panel.removeClass('open');
        }
    });

    // Remove no-transition class after a short delay to enable animations
    setTimeout(function() {
        $('.panel').removeClass('no-transition');
    }, 50);

    // LCARS panel colour cycling across columns (global panel order)
    var $columns = $('.columns');
    if ($columns.length) {
        var variants = ['lcars-variant-1', 'lcars-variant-2', 'lcars-variant-3'];
        $columns.find('.panel').each(function(index) {
            var $panel = $(this);
            $panel.removeClass('lcars-variant-1 lcars-variant-2 lcars-variant-3');
            $panel.addClass(variants[index % variants.length]);
        });
    }

    // Toggle panel on h2 click
    $('.panel > h2').on('click', function() {
        var $panel = $(this).closest('.panel');
        var panelName = $panel.data('panel');

        $panel.toggleClass('open');
        var isOpen = $panel.hasClass('open');
        localStorage.setItem(panelKey + ':' + panelName, isOpen);
        setTimeout(refreshCustomPanelScrollbars, 0);
    });

    window.addEventListener('resize', refreshCustomPanelScrollbars);
    setTimeout(refreshCustomPanelScrollbars, 0);
});
