// Module-level cache
let _jspreadsheetLoadPromise = null;
let _univerLoadPromise = null;
let _plotlyLoadPromise = null;
let _interactjsLoadPromise = null;

async function load_univer() {
    if (window.Univer && window.React && window.ECharts) {
        return;
    }

    if (_univerLoadPromise) {
        return _univerLoadPromise;
    }

    console.log("Loading Univer scripts and styles...");

    _univerLoadPromise = (async () => {
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

        for (const src of scripts) {
            if (document.querySelector(`script[src="${src}"]`)) continue;
            
            await new Promise((resolve, reject) => {
                const script = document.createElement('script');
                script.src = src;
                script.async = true;
                script.onload = () => resolve();
                script.onerror = () => reject(new Error(`Failed to load: ${src}`));
                document.head.appendChild(script);
            });
        }

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
    })();

    return _univerLoadPromise;
}


function load_plotly() {
    if (typeof Plotly !== 'undefined') {
        return Promise.resolve(Plotly);
    }

    if (_plotlyLoadPromise) {
        return _plotlyLoadPromise;
    }

    _plotlyLoadPromise = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = "https://cdn.plot.ly/plotly-3.0.0.min.js";
        script.async = true;

        script.onload = () => {
            resolve(window.Plotly);
        };

        script.onerror = (err) => {
            _plotlyLoadPromise = null;
            reject(new Error('Failed to load Plotly script'));
        };

        document.head.appendChild(script);
    });

    return _plotlyLoadPromise;
}

function load_interactjs() {
    if (typeof interact !== 'undefined') {
        console.log("Interact.js is already loaded.");
        return Promise.resolve(interact);
    }
    if (_interactjsLoadPromise) {
        return _interactjsLoadPromise;
    }
    _interactjsLoadPromise = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = "https://cdn.jsdelivr.net/npm/interactjs/dist/interact.min.js";
        script.async = true;
        script.onload = () => {
            resolve(window.interact);
        };
        script.onerror = (err) => {
            _interactjsLoadPromise = null;
            reject(new Error('Failed to load interact.js script'));
        };
        document.head.appendChild(script);
    });
    console.log("Loading interact.js script...");
    return _interactjsLoadPromise;
}

async function load_jspreadsheet(src) {
    if (window.jspreadsheet && window.jSuites) {
        return;
    }
    if (_jspreadsheetLoadPromise) {
        return _jspreadsheetLoadPromise;
    }
    console.log("Loading JSpreadsheet scripts and styles...");
    _jspreadsheetLoadPromise = (async () => {
        // Load scripts in correct order
        const scripts = [
            'https://cdn.jsdelivr.net/npm/jsuites/dist/jsuites.min.js',
            src // your extension as an argument
        ];
        for (const src of scripts) {
            if (document.querySelector(`script[src="${src}"]`)) continue;
            await new Promise((resolve, reject) => {
                const script = document.createElement('script');
                script.src = src;
                script.async = false;
                script.onload = resolve;
                script.onerror = () => reject(new Error(`Failed to load: ${src}`));
                document.head.appendChild(script);
            });
        }
        // Load all CSS in parallel
        const styles = [
            'https://cdn.jsdelivr.net/npm/jsuites/dist/jsuites.min.css',
            'https://cdn.jsdelivr.net/npm/jspreadsheet-ce@5/dist/jspreadsheet.min.css'
        ];
        const cssPromises = styles.map(href => {
            if (document.querySelector(`link[href="${href}"]`)) return Promise.resolve();
            return new Promise((resolve, reject) => {
                const link = document.createElement('link');
                link.rel = 'stylesheet';
                link.href = href;
                link.type = 'text/css';
                link.onload = resolve;
                link.onerror = () => reject(new Error(`Failed to load CSS: ${href}`));
                document.head.appendChild(link);
            });
        });
        await Promise.all(cssPromises);
    })();
    return _jspreadsheetLoadPromise;
}