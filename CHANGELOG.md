# Registro de cambios

## [1.1.0] - 2026-11-24
- Optimización de CPU en mallas 3D plexus (caché de geometría estática, cálculo aislado para electrones del átomo, empaquetado vectorizado con NumPy y reutilización de proyección para el eco) y vectorización matricial de bandas FFT estéreo en `AudioEngine`.
- Optimización del shader 2D (`ncs_ring.frag`): eliminación de cálculo muerto (`atan`), reutilización del muestreo SDF para el eco, recorte temprano por radio máximo, rotación de constelación precalculada en CPU y modos ligeros para constelación y halos.
- Escalado interno opcional por *framebuffer* (`blit.frag`, `render_scale` de 0.35× a 1.0×) y limitación inteligente de FPS activos y en reposo tanto en ventana como en fondo Wayland.
- Sección **Calidad y rendimiento** en el configurador web (`--ui`) con 5 perfiles (*Máxima*, *Alta*, *Equilibrada*, *Ligera*, *Ultra ahorro*) y controles finos en vivo, más caché de mallas 3D en la vista previa JS.

## [1.0.0] - 2026-11-22
- Lanzamiento inicial multiplataforma (Linux, Windows y macOS).
- Motor estéreo en tiempo real (`parec` en Linux PipeWire/PulseAudio, loopback WASAPI con `soundcard` en Windows y soporte macOS + modo `--demo` integrado).
- 3 niveles independientes con formas básicas 2D (9 predefinidas), lienzo de dibujo simétrico acotado entre circunferencias guía (SDF 2D sin pellizcos) y 8 figuras 3D rotatorias estilo plexus (incluyendo **Esfera plexus** y **Átomo**).
- Líneas de eco por nivel configurables para permanecer invisibles y aparecer solo cerca del máximo de la onda.
- Configurador web local integrado (`resonexuz --ui`) con vista previa animada en vivo y recarga en caliente.
- Modo fondo animado en Wayland (`gtk4-layer-shell`) con soporte multimonitor EGL, y modo ventana/fondo en Windows y macOS.
- Empaquetado Docker (`Dockerfile` + `docker-compose.yml`) y workflows de GitHub Actions (`ci.yml` + `release.yml` para binarios portables en Linux, Windows `.exe` y macOS).
