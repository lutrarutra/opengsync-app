FROM python:3.11-slim

# Install dependencies
RUN apt-get update && apt-get install -y \
    wget \
    xpra \
    xfce4 \
    python3-tk \
    xdg-utils \
    curl \
    dbus-x11 \
    x11-utils \
    qt5-qmake \
    qtbase5-dev \
    libqt5gui5 \
    libqt5core5a \
    libqt5dbus5 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip
RUN python -m pip install napari[pyqt5]
# Expose Xpra web access port
EXPOSE 14500

CMD ["xpra", "start", ":100", "--bind-tcp=0.0.0.0:14500", "--html=on", "--daemon=no", "--start-child=napari"]