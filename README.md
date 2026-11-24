# ResoNexuz

Visualizador de audio estéreo en tiempo real (OpenGL 3.3 / ModernGL) utilizable como **salvapantallas**, **ventana interactiva** o **fondo de pantalla animado**, con configurador web integrado.

## Características principales

- **Audio estéreo real (izquierda / derecha):** el lado izquierdo y derecho de cada forma reaccionan de forma independiente al canal izquierdo y derecho del sistema, con balance cromático configurable.
- **Tres niveles independientes:** cada nivel cuenta con forma propia, tamaño, reactividad, color dinámico (por tono, velocidad del beat e historial espectral) y **eco propio**.
- **Formas híbridas simétricas sin pellizcos:**
  - **9 formas básicas 2D:** círculo, cuadrado redondeado, triángulo, rombo, hexágono, estrella, corazón, mariposa y onda abierta.
  - **Dibujo simétrico libre:** lienzo interactivo con simetría bilateral automática y dos circunferencias guía (interior y exterior) procesadas mediante campo de distancia (SDF 2D).
- **8 figuras 3D rotatorias estilo plexus:** **Esfera geodésica plexus**, **Átomo con electrones en órbita**, octaedro, cubo, pirámide, prisma hexagonal, toroide y extrusión de tu propio dibujo, con facetas translúcidas, aristas luminosas y nodos estrella.
- **Ecos en crestas:** cada nivel puede ocultar su línea de eco en reposo y mostrarla únicamente cuando la onda se acerca al máximo configurable.
- **Perfiles de calidad y rendimiento (`[quality]`):** 5 perfiles listos desde el configurador web (*Máxima*, *Alta*, *Equilibrada*, *Ligera* y *Ultra ahorro*) además de controles individuales para escala de resolución, constelación (completa, solo puntos o apagada), brillo/halos, ecos, facetas/aura 3D y límite de FPS activos y en reposo.
- **Configurador web integrado (`--ui`):** interfaz visual en el navegador (PC, tableta o móvil en red local) con vista previa animada, lienzo de dibujo y recarga en caliente sin reiniciar.

## Compatibilidad por sistema operativo

| Sistema | Captura de audio del sistema | Modos visuales |
|---|---|---|
| **Linux (Wayland / X11)** | PipeWire / PulseAudio (`parec --channels=2`) o `soundcard` | Ventana, salvapantallas a pantalla completa, fondo animado nativo en Wayland (`gtk4-layer-shell`) |
| **Windows 10 / 11** | Loopback WASAPI automático mediante `soundcard` (sin cables virtuales) | Ventana, pantalla completa / salvapantallas, modo fondo detrás de ventanas (`--wallpaper`) |
| **macOS** | Dispositivo virtual (p. ej. BlackHole) mediante `soundcard` o modo `--demo` | Ventana, pantalla completa |

## Instalación rápida

### Linux y macOS
```bash
git clone https://github.com/Anexolocuz/ResoNexuz.git
cd ResoNexuz
./install.sh
```
En Linux con Wayland (Hyprland, Sway, etc.) si deseas el modo de fondo animado en capa inferior (`--wallpaper`), instala `python-gobject`, `gtk4` y `gtk4-layer-shell` desde el gestor de paquetes de tu distribución; el instalador configura el entorno con `--system-site-packages` automáticamente.

### Windows (PowerShell)
```powershell
git clone https://github.com/Anexolocuz/ResoNexuz.git
cd ResoNexuz
.\install.ps1
```

### Instalación manual con pip
```bash
python -m venv .venv
source .venv/bin/activate   # En Windows: .venv\Scripts\activate
pip install -e ".[audio]"
```

### Docker (configurador web y escritorio Linux)
```bash
# Configurador web en http://127.0.0.1:8765 (Linux, Windows y macOS)
docker compose up -d resonexuz-ui

# Visualizador OpenGL en Linux pasando Wayland/PipeWire y GPU (/dev/dri)
docker compose --profile desktop run --rm resonexuz
```
> Nota: en Windows y macOS, Docker corre en una máquina virtual Linux sin acceso directo al audio WASAPI/CoreAudio ni al escritorio nativo, por lo que para el visualizador en esos sistemas usa `install.ps1` o el binario portable de *Releases*.

### Binarios portables (sin instalar Python)
Al publicar una etiqueta `vX.Y.Z`, GitHub Actions compila y adjunta automáticamente los binarios portables para **Linux (`x86_64`)**, **Windows (`.exe`)** y **macOS (`arm64`)** en la sección **Releases**.

## Uso

```bash
# Abrir el visualizador a pantalla completa
resonexuz

# Modo ventana (1280x800) con el configurador web en http://127.0.0.1:8765
resonexuz --windowed --with-ui

# Solo el configurador web para dibujar formas y ajustar parámetros
resonexuz --ui

# Modo fondo de pantalla (Wayland layer-shell en Linux, ventana al fondo en Windows)
resonexuz --wallpaper

# Probar sin música del sistema usando audio sintético estéreo
resonexuz --windowed --demo

# Telemetría del DSP en terminal sin ventana
resonexuz --headless --demo --diag
```

Los ajustes de usuario se guardan en:
- Linux / macOS: `~/.config/resonexuz/` (`config.toml` y `shapes.json`)
- Windows: `%APPDATA%\ResoNexuz\`
- Variable opcional para usar otra carpeta: `RESONEXUZ_CONFIG_DIR`

## Pruebas

```bash
python -m unittest discover -s tests -v
```

## Licencia

Distribuido bajo licencia [MIT](LICENSE).
