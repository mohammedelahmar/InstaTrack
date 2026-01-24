
document.addEventListener('DOMContentLoaded', () => {
    // 1. Staggered Entry Animations
    const animatedElements = document.querySelectorAll('.animate-enter');
    
    // Simple intersection observer to trigger animation when in view
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.animationPlayState = 'running';
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.1 });

    animatedElements.forEach((el, index) => {
        // Add default stagger if not present
        if (!Array.from(el.classList).some(c => c.startsWith('stagger-'))) {
            // Cap stagger at 5 to avoid waiting too long
            const staggerIndex = Math.min(index % 5 + 1, 5);
            el.classList.add(`stagger-${staggerIndex}`);
        }
        el.style.animationPlayState = 'paused'; // Wait for observer
        observer.observe(el);
    });

    // 2. Table Filtering
    setupTableFiltering();
});

function setupTableFiltering() {
    const table = document.querySelector('.data-table');
    if (!table) return;

    // Create search input
    const p = table.parentElement;
    const controls = document.createElement('div');
    controls.className = 'table-controls';
    
    const search = document.createElement('input');
    search.type = 'text';
    search.placeholder = 'Filtrer les événements...';
    search.className = 'search-input';
    
    controls.appendChild(search);
    p.insertBefore(controls, table);

    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));

    search.addEventListener('input', (e) => {
        const term = e.target.value.toLowerCase();
        
        requestAnimationFrame(() => {
            rows.forEach(row => {
                const text = row.textContent.toLowerCase();
                row.style.display = text.includes(term) ? '' : 'none';
            });
        });
    });
}
