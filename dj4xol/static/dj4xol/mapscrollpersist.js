$("document").ready( function() {
 var posX = localStorage.getItem('posX');
 $("#starmap").scrollLeft(posX);
 var posY = localStorage.getItem('posY');
 $("#starmap").scrollTop(posY);
 console.log("ready");
 console.log(posX);
 console.log(posY);

$("a").on('click', function() {
 var posX = ($("#starmap").scrollLeft());
 var posY = ($("#starmap").scrollTop());
 localStorage.setItem('posX', posX);
 localStorage.setItem('posY', posY);
 console.log("click");
 console.log(posX);
 console.log(posY);
}); });
