# AI Task Assistant

Asistente de tareas local con IA (Ollama), transcripción de voz (Whisper),
bot de Telegram y dashboard en Grafana. Corre 100% local en QNAP con Docker.

## Servicios

| Servicio   | Puerto | Descripción                      |
|------------|--------|----------------------------------|
| Backend    | 8000   | FastAPI + Bot Telegram           |
| Whisper    | 9000   | Transcripción de audio           |
| Ollama     | 11434  | LLM local (llama3.2)             |
| PostgreSQL | 5432   | Base de datos principal          |
| Redis      | 6379   | Cache y colas                    |
| Grafana    | 3000   | Dashboard de visualización       |
| Nginx      | 80     | Proxy reverso (entry point)      |

## Inicio rápido

```bash
cp .env.example .env
# Editar .env con tus credenciales
bash setup.sh
```

## Comandos útiles

```bash
# Ver logs del bot
docker logs -f ai_backend

# Ver estado de todos los servicios
docker-compose ps

# Detener todo
docker-compose down

# Reiniciar un servicio
docker-compose restart backend

# Descargar otro modelo de Ollama
docker exec ai_ollama ollama pull mistral
```

## Bot de Telegram — Comandos

| Comando        | Acción                          |
|----------------|---------------------------------|
| /start         | Ver ayuda                       |
| /tareas        | Listar todas las tareas         |
| /pendientes    | Ver tareas pendientes           |
| /completar ID  | Marcar tarea como completada    |
| Texto libre    | Crear tarea desde texto         |
| Nota de voz    | Transcribir y crear tarea       |
