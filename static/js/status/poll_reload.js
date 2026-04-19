document.addEventListener("DOMContentLoaded", function () {
  var el = document.querySelector("[data-task-state]");
  if (!el) return;

  var state = (el.getAttribute("data-task-state") || "").toUpperCase();
  var runningStates = new Set(["PENDING", "STARTED", "RETRY", "PROGRESS", "RECEIVED"]);

  if (!runningStates.has(state)) return;

  // Gentle polling so operators don't need to refresh.
  setTimeout(function () {
    window.location.reload();
  }, 5000);
});

