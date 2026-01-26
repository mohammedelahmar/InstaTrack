
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

    // 3. Profile Modal
    setupProfileModal();
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

function setupProfileModal() {
    const modal = document.getElementById('profileModal');
    if (!modal) return;

    const closeBtn = modal.querySelector('.profile-close');
    const els = {
        avatar: document.getElementById('p-avatar'),
        badge: document.getElementById('p-badge'),
        fullname: document.getElementById('p-fullname'),
        username: document.getElementById('p-username'),
        posts: document.getElementById('p-posts'),
        followers: document.getElementById('p-followers'),
        following: document.getElementById('p-following'),
        bio: document.getElementById('p-bio'),
        link: document.getElementById('p-link'),
        linkText: document.getElementById('p-link-text'),
        private: document.getElementById('p-private'),
        public: document.getElementById('p-public'),
        followsYou: document.getElementById('p-follows-you'),
        notFollowsYou: document.getElementById('p-not-follows-you'),
        copyBio: document.getElementById('p-copy-bio'),
    };

    const formatNumber = (num) => {
        return new Intl.NumberFormat('en-US', { notation: "compact", maximumFractionDigits: 1 }).format(num || 0);
    };

    const extractDomain = (url) => {
        try {
            return new URL(url).hostname.replace('www.', '');
        } catch (e) {
            return url;
        }
    };

    const openModal = async (username) => {
        modal.showModal();
        
        // Reset state
        els.avatar.src = ""; // Clear old image
        els.fullname.textContent = "Chargement...";
        els.username.textContent = `@${username}`;
        els.posts.textContent = "-";
        els.followers.textContent = "-";
        els.following.textContent = "-";
        els.bio.textContent = "";

        // Force hide everything
        const hide = (el) => { if(el) { el.hidden = true; el.style.display = 'none'; } };
        const show = (el, type = 'block') => { if(el) { el.hidden = false; el.style.display = type; } };

        hide(els.link);
        hide(els.badge);
        hide(els.copyBio);
        hide(els.private);
        hide(els.public);
        hide(els.followsYou);
        hide(els.notFollowsYou);

        hide(els.notFollowsYou);

        try {
            // Get target account from config
            const configEl = document.getElementById('dashboard-config');
            const config = configEl ? JSON.parse(configEl.textContent) : {};
            const target = config.default_account || '';

            const res = await fetch(`/api/profile/${username}?target=${encodeURIComponent(target)}`);
            const data = await res.json();
            if (data.status !== 'ok') throw new Error(data.message);

            const p = data.profile;
            
            // Populate
            if (p.profile_pic_url) {
                els.avatar.src = `/api/proxy/image?url=${encodeURIComponent(p.profile_pic_url)}`;
            }
            
            els.fullname.textContent = p.full_name || username;
            els.username.textContent = `@${p.username}`;
            
            if (p.is_verified) {
                show(els.badge, 'flex');
            } else {
                hide(els.badge);
            }
            
            els.posts.textContent = formatNumber(p.media_count);
            els.followers.textContent = formatNumber(p.follower_count);
            els.following.textContent = formatNumber(p.following_count);
            
            if (p.biography) {
                els.bio.textContent = p.biography;
                show(els.copyBio, 'inline-flex');
                
                // Copy functionality
                els.copyBio.onclick = () => {
                    navigator.clipboard.writeText(p.biography).then(() => {
                        const originalHtml = els.copyBio.innerHTML;
                        els.copyBio.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="#4ade80" stroke-width="2"><path d="M20 6L9 17l-5-5"></path></svg>`;
                        setTimeout(() => els.copyBio.innerHTML = originalHtml, 2000);
                    });
                };
            } else {
                els.bio.textContent = "";
                hide(els.copyBio);
            }

            if (p.external_url) {
                els.link.href = p.external_url;
                els.linkText.textContent = extractDomain(p.external_url);
                show(els.link, 'inline-flex');
            } else {
                hide(els.link);
            }

             // Privacy Badge
             if (p.is_private) {
                show(els.private, 'inline-flex');
                hide(els.public);
            } else {
                hide(els.private);
                show(els.public, 'inline-flex');
            }

             // Friendship Badges
            // Follows You: They follow me
            if (p.follows_viewer === true) {
                show(els.followsYou, 'inline-flex');
            } else {
                hide(els.followsYou);
            }

            // Doesn't Follow Back: I follow them (followed_by_viewer) BUT they don't follow me (follows_viewer is false)
            if (p.followed_by_viewer === true && !p.follows_viewer) {
                show(els.notFollowsYou, 'inline-flex');
            } else {
                hide(els.notFollowsYou);
            }

        } catch (err) {
            els.fullname.textContent = "Erreur";
            els.bio.textContent = "Impossible de charger le profil.";
            console.error(err);
        }
    };

    closeBtn.addEventListener('click', () => modal.close());
    modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.close();
    });

    // Delegate clicks
    document.body.addEventListener('click', (e) => {
        const item = e.target.closest('.user-item, tr');
        if (!item) return;
        
        if (e.target.closest('a, button')) return;

        const username = item.dataset.username;
        if (username && username !== 'None' && username !== '') {
            openModal(username);
        }
    });
}
