# Guide d'utilisation de la colonne file_metadata dans File

La colonne `file_metadata` (type JSONB) a été ajoutée à la table `files` via la migration v2. Elle permet de stocker des informations personnalisées sur chaque fichier de manière flexible.

## Caractéristiques

- **Type**: PostgreSQL JSONB (JSON binaire optimisé)
- **Valeur par défaut**: `{}`
- **Indexé**: Oui (index GIN pour recherches rapides)
- **Ajoutée dans**: Migration tenant v2

## Méthodes disponibles

### 1. `get_metadata(key, default=None)`

Récupère une valeur de métadonnée.

```python
# Récupérer une valeur avec défaut
mime_type = file.get_metadata('mime_type', 'application/octet-stream')

# Récupérer une valeur qui peut être None
encoding = file.get_metadata('encoding')
```

### 2. `set_metadata(key, value)`

Définit une valeur de métadonnée.

```python
# Valeur simple
file.set_metadata('mime_type', 'image/png')

# Valeur complexe (dict)
file.set_metadata('dimensions', {'width': 1920, 'height': 1080})

# Valeur complexe (array)
file.set_metadata('tags', ['important', 'contract', '2024'])
```

### 3. `update_metadata(data)`

Met à jour plusieurs métadonnées en une fois.

```python
file.update_metadata({
    'mime_type': 'image/jpeg',
    'width': 1920,
    'height': 1080,
    'color_space': 'RGB',
    'exif': {
        'camera': 'Canon EOS 5D',
        'iso': 400
    }
})
```

### 4. `has_metadata(key)`

Vérifie si une clé existe.

```python
if file.has_metadata('virus_scan_result'):
    result = file.get_metadata('virus_scan_result')
else:
    # Lancer le scan
    pass
```

### 5. `remove_metadata(key)`

Supprime une métadonnée.

```python
if file.remove_metadata('temp_flag'):
    print("Flag temporaire supprimé")
```

## Cas d'usage courants

### 1. Informations techniques sur les images

```python
file.update_metadata({
    'mime_type': 'image/jpeg',
    'width': 1920,
    'height': 1080,
    'color_space': 'RGB',
    'dpi': 72,
    'has_alpha': False,
    'orientation': 'landscape'
})
```

### 2. Métadonnées EXIF

```python
file.set_metadata('exif', {
    'camera': 'Canon EOS 5D Mark IV',
    'lens': 'EF 24-70mm f/2.8L II USM',
    'iso': 400,
    'aperture': 'f/2.8',
    'shutter_speed': '1/200',
    'focal_length': '50mm',
    'date_taken': '2024-01-15T14:30:00Z',
    'gps': {
        'latitude': 48.8566,
        'longitude': 2.3522
    }
})
```

### 3. Résultats d'analyse (OCR, virus scan)

```python
# Scan antivirus
file.update_metadata({
    'virus_scan': {
        'scanned_at': '2024-01-15T10:00:00Z',
        'scanner': 'ClamAV 1.0.0',
        'status': 'clean',
        'threats_found': 0
    },
    'is_safe': True
})

# OCR pour documents
file.update_metadata({
    'ocr': {
        'language': 'fr',
        'confidence': 0.95,
        'text_preview': 'Contrat de location...',
        'page_count': 15,
        'has_text_layer': True
    }
})
```

### 4. Miniatures générées

```python
file.set_metadata('thumbnails', {
    'small': {
        'width': 200,
        'height': 150,
        's3_path': 'thumbnails/small/abc123.jpg'
    },
    'medium': {
        'width': 800,
        'height': 600,
        's3_path': 'thumbnails/medium/abc123.jpg'
    },
    'large': {
        'width': 1600,
        'height': 1200,
        's3_path': 'thumbnails/large/abc123.jpg'
    }
})
```

### 5. Métadonnées vidéo

```python
file.update_metadata({
    'mime_type': 'video/mp4',
    'duration_seconds': 3600,
    'video_codec': 'h264',
    'audio_codec': 'aac',
    'resolution': '1920x1080',
    'framerate': 30,
    'bitrate_kbps': 5000,
    'has_subtitles': True,
    'subtitle_languages': ['en', 'fr']
})
```

### 6. Système de tags et catégories

```python
file.update_metadata({
    'tags': ['important', 'contract', '2024', 'legal'],
    'category': 'legal',
    'subcategory': 'contracts',
    'department': 'sales',
    'project': 'Project Alpha',
    'confidentiality': 'internal'
})
```

### 7. État de traitement

```python
file.update_metadata({
    'processing_status': 'in_progress',
    'processing_steps': {
        'uploaded': {
            'status': 'completed',
            'timestamp': '2024-01-15T10:00:00Z'
        },
        'virus_scan': {
            'status': 'in_progress',
            'started_at': '2024-01-15T10:01:00Z'
        },
        'ocr': {
            'status': 'pending'
        },
        'thumbnail': {
            'status': 'pending'
        }
    }
})
```

## Recherche avec PostgreSQL JSONB

PostgreSQL offre des opérateurs puissants pour interroger les données JSONB :

### Recherche par valeur exacte

```python
# Tous les fichiers JPEG
jpeg_files = File.query.filter(
    File.file_metadata['mime_type'].astext == 'image/jpeg'
).all()
```

### Recherche numérique

```python
from sqlalchemy import cast, Integer

# Images de plus de 1920px de large
large_images = File.query.filter(
    cast(File.file_metadata['width'].astext, Integer) > 1920
).all()
```

### Recherche dans un array

```python
# Fichiers avec le tag 'important'
important_files = File.query.filter(
    File.file_metadata['tags'].contains(['important'])
).all()
```

### Vérifier l'existence d'une clé

```python
# Fichiers qui ont des données EXIF
files_with_exif = File.query.filter(
    File.file_metadata.has_key('exif')
).all()
```

### Recherche dans des objets imbriqués

```python
# Fichiers pris avec un appareil Canon
canon_photos = File.query.filter(
    File.file_metadata['exif']['camera'].astext.like('%Canon%')
).all()
```

## Bonnes pratiques

### 1. **Initialisez file_metadata lors de la création**

```python
file = File(
    md5_hash='abc123...',
    s3_path='...',
    file_size=1024000,
    created_by='user-uuid'
)

# Initialiser avec des métadonnées de base
file.update_metadata({
    'mime_type': 'image/jpeg',
    'original_filename': 'photo.jpg',
    'uploaded_at': datetime.utcnow().isoformat()
})
```

### 2. **Utilisez des clés cohérentes**

Définissez un standard de nommage pour vos clés :

```python
# ✓ Bon - snake_case cohérent
file.set_metadata('mime_type', 'image/jpeg')
file.set_metadata('upload_timestamp', '...')

# ✗ Éviter - incohérent
file.set_metadata('mimeType', 'image/jpeg')
file.set_metadata('upload-timestamp', '...')
```

### 3. **Validez les données avant stockage**

```python
def set_image_metadata(file, width, height):
    if not isinstance(width, int) or width <= 0:
        raise ValueError("Invalid width")
    if not isinstance(height, int) or height <= 0:
        raise ValueError("Invalid height")

    file.update_metadata({
        'width': width,
        'height': height
    })
```

### 4. **N'oubliez pas de commit**

```python
file.set_metadata('processed', True)
db.session.commit()  # Important !
```

### 5. **Utilisez des valeurs par défaut**

```python
# Au lieu de
mime = file.file_metadata.get('mime_type') if file.file_metadata else None

# Préférez
mime = file.get_metadata('mime_type', 'application/octet-stream')
```

## Performance

### Index GIN

La colonne `file_metadata` est indexée avec un index GIN (Generalized Inverted Index), ce qui permet des recherches rapides :

```sql
CREATE INDEX IF NOT EXISTS idx_files_metadata ON files USING GIN (file_metadata);
```

### Requêtes optimisées

```python
# ✓ Utilise l'index - rapide
File.query.filter(File.file_metadata['mime_type'].astext == 'image/jpeg')

# ✗ Full table scan - lent
File.query.filter(File.file_metadata.cast(String).like('%jpeg%'))
```

## Exemples complets

Voir le fichier [examples/file_metadata_usage.py](../examples/file_metadata_usage.py) pour des exemples d'utilisation complets et des cas d'usage réels.

## Migration

Cette fonctionnalité a été ajoutée via la migration tenant v2. Pour les tenants existants, exécutez :

```bash
# Appliquer aux tenants existants
docker-compose exec api python scripts/migrate_all_tenants.py

# Nouveaux tenants : migrations automatiques lors de la création
```

## Support

- PostgreSQL JSONB : [Documentation officielle](https://www.postgresql.org/docs/current/datatype-json.html)
- SQLAlchemy JSONB : [Documentation](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#sqlalchemy.dialects.postgresql.JSONB)
