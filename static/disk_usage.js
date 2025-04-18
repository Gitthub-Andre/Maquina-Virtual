document.addEventListener('DOMContentLoaded', function() {
    var bar = document.getElementById('diskUsageBar');
    var percent = Number(bar.dataset.percent || 0);
    bar.style.width = percent + '%';
});
