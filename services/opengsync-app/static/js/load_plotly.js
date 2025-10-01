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