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

## Tests

Para ejecutar las pruebas:

```bash
python -m pytest tests/ -v
```

Los tests incluyen:
- Tests unitarios para cada módulo del core
- Tests de integración que validan el pipeline completo
- Tests del modo demo
