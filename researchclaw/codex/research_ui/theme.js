// Apply stored preference before paint; CSS follows live system changes.
try { const value=localStorage.getItem('research-theme'); document.documentElement.dataset.theme=['light','dark'].includes(value)?value:'system'; } catch { document.documentElement.dataset.theme='system'; }
