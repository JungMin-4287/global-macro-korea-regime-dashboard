(() => {
  const main = document.querySelector('main');
  const titles = [...main.querySelectorAll(':scope > .section-title')];
  const jumps = document.getElementById('sectionJumps');
  const shortNames = ['수급·변동성', '국내시장', 'SOX', 'PER', '감익', '반등조건', '시장폭'];

  const groups = titles.map((title, index) => {
    const content = title.nextElementSibling;
    if (!content || !content.classList.contains('grid')) return null;
    const details = document.createElement('details');
    details.className = 'dashboard-group';
    details.id = `dashboard-section-${index + 1}`;
    const summary = document.createElement('summary');
    summary.textContent = title.textContent;
    title.before(details);
    details.append(summary, content);
    title.remove();

    const jump = document.createElement('button');
    jump.type = 'button';
    jump.className = 'jump-button';
    jump.textContent = shortNames[index] || `구간 ${index + 1}`;
    jump.addEventListener('click', () => {
      details.open = true;
      details.scrollIntoView({behavior: 'smooth', block: 'start'});
    });
    jumps?.appendChild(jump);

    details.addEventListener('toggle', () => {
      if (details.open) requestAnimationFrame(() => {
        if (window.Chart?.instances) Object.values(Chart.instances).forEach(chart => chart.resize());
      });
    });
    return details;
  }).filter(Boolean);

  document.getElementById('collapseAll')?.addEventListener('click', () => {
    groups.forEach(group => { group.open = false; });
    document.getElementById('trendGate')?.scrollIntoView({behavior: 'smooth', block: 'start'});
  });
  document.getElementById('expandAll')?.addEventListener('click', () => {
    groups.forEach(group => { group.open = true; });
  });
})();
