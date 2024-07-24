function openFullscreen() {
  var elem = document.getElementById("dashboard");
  /* Note that we must include prefixes for different browsers, as they don't support the requestFullscreen method yet */
  if (elem.requestFullscreen) {
    elem.requestFullscreen();
  } else if (elem.webkitRequestFullscreen) { /* Safari */
    elem.webkitRequestFullscreen();
  } else if (elem.msRequestFullscreen) { /* IE11 */
    elem.msRequestFullscreen();
  }
}
