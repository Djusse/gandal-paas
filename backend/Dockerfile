FROM python:3.12-slim

# Éviter la mise en cache des fichiers .pyc et activer le streaming direct des logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Installation des dépendances système minimales (curl pour le healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Mise en cache de l'installation des dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie du code source du projet (les exclusions sont gérées par .dockerignore)
COPY . .

# Création d'un utilisateur non-root pour des raisons de sécurité
RUN useradd -m -u 1000 app && chown -R app:app /app
USER app

EXPOSE 8000

# Vérification de santé du conteneur API
HEALTHCHECK --interval=20s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Exécution des migrations Alembic avant le démarrage du serveur ASGI Uvicorn
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
