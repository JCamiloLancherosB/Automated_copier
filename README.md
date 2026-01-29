# MediaCopier

## Objetivo

MediaCopier es un proyecto base para automatizar copias de archivos multimedia.
Esta versión inicial solo incluye una interfaz mínima de ejemplo.

## Cómo ejecutar

1. Instala el proyecto en modo editable:

   ```bash
   python -m pip install -e .[dev]
   ```

2. Ejecuta la aplicación (UI):

   ```bash
   python -m mediacopier
   ```

## Modo Demo

El modo demo permite probar el pipeline completo sin necesidad de archivos externos:

```bash
# Ver información sobre el modo demo
python -m mediacopier --demo-info

# Ejecutar demostración completa del pipeline
python -m mediacopier --demo
```

El modo demo:
- Crea archivos temporales de prueba (canciones y películas)
- Ejecuta el pipeline completo: catálogo → match → plan → dry-run
- Muestra estadísticas de resultados
- Limpia archivos temporales automáticamente

## Ejemplo de uso

```bash
python -m mediacopier
```

Se abrirá una interfaz gráfica con el panel de configuración y la cola de trabajos.

## Integración con TechAura Chatbot

MediaCopier puede integrarse con el chatbot de TechAura para recibir y procesar
pedidos de grabación USB automáticamente.

### Configuración de Variables de Entorno

Configura las siguientes variables de entorno para conectar con el API de TechAura:

```bash
# URL del API de TechAura (por defecto: http://localhost:3006)
export TECHAURA_API_URL="https://api.techaura.com"

# Clave de API para autenticación (opcional)
export TECHAURA_API_KEY="tu-api-key-aquí"
```

### Estructura de Carpetas de Contenido

Para que la integración funcione correctamente, organiza tu contenido multimedia
en las siguientes carpetas:

```
/media/
├── music/          # Carpeta con archivos de música (.mp3, .flac, .wav, .m4a)
│   ├── salsa/
│   ├── merengue/
│   ├── rock/
│   └── ...
├── videos/         # Carpeta con videos (.mp4, .mkv, .avi, .mov)
│   └── ...
└── movies/         # Carpeta con películas (.mp4, .mkv, .avi)
    └── ...
```

### Uso Programático

Puedes configurar la integración programáticamente:

```python
from mediacopier.ui.window import MediaCopierUI

app = MediaCopierUI()

# Configurar integración con TechAura
app.setup_techaura_integration(
    content_sources={
        "music": "/media/music",
        "videos": "/media/videos",
        "movies": "/media/movies",
    },
    api_url="https://api.techaura.com",  # Opcional
    api_key="tu-api-key",                 # Opcional
)

app.mainloop()
```

### Flujo de Trabajo Completo

1. **Recepción de pedidos**: El chatbot de TechAura recibe pedidos de clientes
   con sus preferencias (géneros, artistas, etc.)

2. **Actualizar pedidos**: En la UI, haz clic en "Actualizar pedidos" en el
   panel "Pedidos TechAura" para obtener los pedidos pendientes.

3. **Revisar detalles**: Selecciona un pedido para ver sus detalles (cliente,
   tipo de contenido, géneros/artistas seleccionados).

4. **Seleccionar USB**: Conecta la USB de destino y selecciónala en el campo
   "Destino (USB detectadas)".

5. **Confirmar grabación**: Haz clic en "Confirmar y grabar" para crear un
   trabajo de copia. Se mostrará un diálogo de confirmación con todos los
   detalles.

6. **Ejecutar grabación**: El trabajo se agregará a la cola. Selecciónalo y
   haz clic en "Ejecutar" para iniciar la copia.

7. **Notificación automática**: Al completar o fallar la grabación, se
   notificará automáticamente al sistema de TechAura para actualizar el
   estado del pedido.

### Callbacks de Estado

El procesador de órdenes notifica automáticamente al API de TechAura sobre
el estado de las grabaciones:

- **Inicio**: Cuando comienza la grabación de un pedido
- **Completado**: Cuando la grabación finaliza exitosamente
- **Error**: Cuando ocurre un error durante la grabación

## Tests

Para ejecutar las pruebas:

```bash
python -m pytest tests/ -v
```

Los tests incluyen:
- Tests unitarios para cada módulo del core
- Tests de integración que validan el pipeline completo
- Tests del modo demo
- Tests del procesador de órdenes de TechAura
