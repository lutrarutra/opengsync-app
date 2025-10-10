async function load_univer() {
    const scripts = [
        'https://unpkg.com/react@18.3.1/umd/react.production.min.js',
        'https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js',
        'https://unpkg.com/rxjs/dist/bundles/rxjs.umd.min.js',
        'https://unpkg.com/echarts@5.6.0/dist/echarts.min.js',
        'https://unpkg.com/@univerjs/presets/lib/umd/index.js',
        'https://unpkg.com/@univerjs/preset-sheets-core/lib/umd/index.js',
        'https://unpkg.com/@univerjs/preset-sheets-core/lib/umd/locales/en-US.js',
        'https://unpkg.com/@univerjs/preset-sheets-data-validation/lib/umd/index.js',
        'https://unpkg.com/@univerjs/preset-sheets-data-validation/lib/umd/locales/en-US.js'
    ];

    const styles = [
        'https://unpkg.com/@univerjs/preset-sheets-core/lib/index.css',
        'https://unpkg.com/@univerjs/preset-sheets-data-validation/lib/index.css'
    ];

    // Load scripts ONE BY ONE
    for (const src of scripts) {
        // Skip if already loaded
        if (document.querySelector(`script[src="${src}"]`)) continue;

        await new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = src;
            script.async = true; // still async download, but we await execution
            script.onload = () => resolve();
            script.onerror = () => reject(new Error(`Failed to load: ${src}`));
            document.head.appendChild(script);
        });
    }

    // Load CSS (can be parallel — less critical)
    const cssPromises = styles.map(href => {
        if (document.querySelector(`link[href="${href}"]`)) return Promise.resolve();
        return new Promise((resolve, reject) => {
            const link = document.createElement('link');
            link.rel = 'stylesheet';
            link.href = href;
            link.onload = resolve;
            link.onerror = () => reject(new Error(`Failed to load CSS: ${href}`));
            document.head.appendChild(link);
        });
    });

    await Promise.all(cssPromises);
}

function load_plotly() {
    return new Promise((resolve) => {
        if (typeof Plotly !== 'undefined') {
            return resolve(Plotly);
        }
        const script = document.createElement('script');
        script.src = "https://cdn.plot.ly/plotly-3.0.0.min.js";
        script.onload = () => resolve(window.Plotly);
        document.head.appendChild(script);
    });
}