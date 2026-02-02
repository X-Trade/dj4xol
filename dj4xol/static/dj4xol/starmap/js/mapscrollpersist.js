// Global function for destination selection mode (called from star link onclick)
function submitDestination(starId, x, y) {
    // Get current URL params and update with destination
    var params = new URLSearchParams(window.location.search);
    params.delete('mode');  // Exit destination mode
    params.set('dest_star', starId);
    params.delete('dest_x');
    params.delete('dest_y');
    window.location.search = params.toString();
}

// Submit coordinate-based destination (for empty space clicks)
function submitCoordinateDestination(x, y) {
    var params = new URLSearchParams(window.location.search);
    params.delete('mode');  // Exit destination mode
    params.delete('dest_star');
    params.set('dest_x', x);
    params.set('dest_y', y);
    window.location.search = params.toString();
}

$("document").ready(function() {
    var $starmap = $("#starmap");
    var $maparea = $("#maparea");
    var $sizer = $("#maparea-sizer");

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

    if (locateEnabled && urlX !== null && urlY !== null && !destMode) {
        // Center on selected coordinates (multiply by MAP_SCALE=6, add border offset)
        var targetX = (parseInt(urlX) * mapScale + borderOffset) * zoomLevel;
        var targetY = (parseInt(urlY) * mapScale + borderOffset) * zoomLevel;
        $starmap.scrollLeft(targetX - $starmap.width() / 2);
        $starmap.scrollTop(targetY - $starmap.height() / 2);

        // Show locate animation if requested
        if (urlLocate === '1') {
            showLocateAnimation(urlX, urlY);
        }
    } else {
        // Restore scroll position from localStorage
        var posX = localStorage.getItem(storageKey + ':posX');
        var posY = localStorage.getItem(storageKey + ':posY');
        $starmap.scrollLeft(posX);
        $starmap.scrollTop(posY);
    }

    // Save scroll position and zoom before page unload
    $(window).bind('beforeunload', function() {
        localStorage.setItem(storageKey + ':posX', $starmap.scrollLeft());
        localStorage.setItem(storageKey + ':posY', $starmap.scrollTop());
        localStorage.setItem(storageKey + ':zoom', zoomLevel);
    });

    // Click+drag scrolling
    var isDragging = false;
    var hasDragged = false;
    var startX, startY, scrollLeft, scrollTop;

    $starmap.on('mousedown', function(e) {
        // Don't drag if clicking on a control or link
        if ($(e.target).closest('.starmap-controls, a').length) return;
        isDragging = true;
        hasDragged = false;
        startX = e.pageX - $starmap.offset().left;
        startY = e.pageY - $starmap.offset().top;
        scrollLeft = $starmap.scrollLeft();
        scrollTop = $starmap.scrollTop();
    });

    $(document).on('mouseup', function() {
        isDragging = false;
        // Reset hasDragged after a short delay so click handler can check it
        setTimeout(function() { hasDragged = false; }, 0);
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
        $starmap.scrollLeft(newContentX - viewportX);
        $starmap.scrollTop(newContentY - viewportY);
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
        e.preventDefault();
        var delta = e.originalEvent.deltaY > 0 ? -zoomStep : zoomStep;

        // Get mouse position relative to starmap viewport
        var offset = $starmap.offset();
        var viewportX = (e.originalEvent.pageX || e.pageX) - offset.left;
        var viewportY = (e.originalEvent.pageY || e.pageY) - offset.top;

        zoomTo(zoomLevel + delta, viewportX, viewportY);
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

            // Reverse the coordinate transformation: pixel -> map coordinate
            // pixel = mapCoord * MAP_SCALE + borderOffset
            // mapCoord = (pixel - borderOffset) / MAP_SCALE
            var mapX = Math.round((unscaledX - borderOffset) / mapScale);
            var mapY = Math.round((unscaledY - borderOffset) / mapScale);

            submitCoordinateDestination(mapX, mapY);
        });
    }

    // Messages scroll persistence
    var $messagesScroll = $('#messages-scroll');
    var $messages = $('#messages');
    if ($messagesScroll.length && $messages.length) {
        var messagesKey = storageKey + ':messages';
        var currentYear = $messages.data('year');
        var savedYear = localStorage.getItem(messagesKey + ':year');
        var savedScroll = localStorage.getItem(messagesKey + ':scroll');

        // Restore scroll position only if same year
        if (savedYear && parseInt(savedYear) === currentYear && savedScroll) {
            $messagesScroll.scrollTop(parseInt(savedScroll));
        }

        // Save scroll position on scroll
        $messagesScroll.on('scroll', function() {
            localStorage.setItem(messagesKey + ':scroll', $messagesScroll.scrollTop());
            localStorage.setItem(messagesKey + ':year', currentYear);
        });
    }
});
