$("document").ready(function() {
    var $starmap = $("#starmap");

    // Restore scroll position from localStorage
    var posX = localStorage.getItem('posX');
    var posY = localStorage.getItem('posY');
    $starmap.scrollLeft(posX);
    $starmap.scrollTop(posY);

    // Save scroll position before page unload
    $(window).bind('beforeunload', function() {
        localStorage.setItem('posX', $starmap.scrollLeft());
        localStorage.setItem('posY', $starmap.scrollTop());
    });

    // Click+drag scrolling
    var isDragging = false;
    var startX, startY, scrollLeft, scrollTop;

    $starmap.on('mousedown', function(e) {
        isDragging = true;
        startX = e.pageX - $starmap.offset().left;
        startY = e.pageY - $starmap.offset().top;
        scrollLeft = $starmap.scrollLeft();
        scrollTop = $starmap.scrollTop();
    });

    $(document).on('mouseup', function() {
        isDragging = false;
    });

    $(document).on('mousemove', function(e) {
        if (!isDragging) return;
        e.preventDefault();
        var x = e.pageX - $starmap.offset().left;
        var y = e.pageY - $starmap.offset().top;
        var walkX = (x - startX);
        var walkY = (y - startY);
        $starmap.scrollLeft(scrollLeft - walkX);
        $starmap.scrollTop(scrollTop - walkY);
    });
});
