"""
Exemples d'utilisation de la colonne metadata dans le modèle File

Ce fichier montre comment utiliser la nouvelle colonne JSONB 'metadata'
ajoutée par la migration v2 pour stocker des informations personnalisées
sur les fichiers.

La colonne metadata permet de stocker :
- Informations techniques (MIME type, encoding, résolution, etc.)
- Métadonnées EXIF pour les images
- Résultats d'analyse (scan antivirus, OCR, etc.)
- Tags et catégories personnalisés
- Toute autre information JSON-serializable
"""

from app import create_app
from app.models.file import File
from app.extensions import db


def example_1_basic_metadata():
    """Exemple 1: Utilisation basique - stocker le MIME type"""

    # Créer ou récupérer un fichier
    file = File.query.first()

    if file:
        # Définir des métadonnées simples
        file.set_metadata('mime_type', 'image/jpeg')
        file.set_metadata('encoding', 'utf-8')

        db.session.commit()

        # Récupérer les métadonnées
        mime = file.get_metadata('mime_type')
        encoding = file.get_metadata('encoding', 'unknown')

        print(f"File: {file.md5_hash}")
        print(f"  MIME type: {mime}")
        print(f"  Encoding: {encoding}")


def example_2_image_metadata():
    """Exemple 2: Stocker les métadonnées d'une image"""

    file = File.query.first()

    if file:
        # Mettre à jour plusieurs métadonnées en une fois
        file.update_metadata({
            'mime_type': 'image/jpeg',
            'width': 1920,
            'height': 1080,
            'color_space': 'RGB',
            'has_alpha': False,
            'dpi': 72,
            'exif': {
                'camera': 'Canon EOS 5D Mark IV',
                'lens': 'EF 24-70mm f/2.8L II USM',
                'iso': 400,
                'aperture': 'f/2.8',
                'shutter_speed': '1/200',
                'focal_length': '50mm',
                'date_taken': '2024-01-15T14:30:00Z'
            }
        })

        db.session.commit()

        # Accéder aux métadonnées imbriquées
        exif = file.get_metadata('exif', {})
        print(f"Photo taken with: {exif.get('camera')}")
        print(f"Dimensions: {file.get_metadata('width')}x{file.get_metadata('height')}")


def example_3_document_analysis():
    """Exemple 3: Stocker les résultats d'analyse de document"""

    file = File.query.first()

    if file:
        # Résultats d'analyse OCR
        file.update_metadata({
            'mime_type': 'application/pdf',
            'page_count': 15,
            'has_text_layer': True,
            'language': 'fr',
            'ocr_confidence': 0.95,
            'ocr_text_preview': 'Contrat de location...',
            'detected_entities': ['date', 'address', 'person_name'],
            'is_searchable': True
        })

        db.session.commit()

        print(f"Document: {file.md5_hash}")
        print(f"  Pages: {file.get_metadata('page_count')}")
        print(f"  OCR confidence: {file.get_metadata('ocr_confidence')*100}%")


def example_4_virus_scan():
    """Exemple 4: Stocker les résultats d'un scan antivirus"""

    file = File.query.first()

    if file:
        # Résultats de scan
        file.update_metadata({
            'virus_scan': {
                'scanned_at': '2024-01-15T10:00:00Z',
                'scanner': 'ClamAV 1.0.0',
                'status': 'clean',
                'threats_found': 0,
                'scan_duration_ms': 125
            },
            'is_safe': True
        })

        db.session.commit()

        # Vérifier si le fichier a été scanné
        if file.has_metadata('virus_scan'):
            scan = file.get_metadata('virus_scan')
            print(f"File scanned: {scan['status']}")
        else:
            print("File not yet scanned")


def example_5_video_metadata():
    """Exemple 5: Métadonnées vidéo"""

    file = File.query.first()

    if file:
        file.update_metadata({
            'mime_type': 'video/mp4',
            'duration_seconds': 3600,
            'video_codec': 'h264',
            'audio_codec': 'aac',
            'resolution': '1920x1080',
            'framerate': 30,
            'bitrate_kbps': 5000,
            'has_subtitles': True,
            'subtitle_languages': ['en', 'fr'],
            'thumbnail_generated': True,
            'thumbnail_s3_path': 'thumbnails/...'
        })

        db.session.commit()


def example_6_custom_tags():
    """Exemple 6: Système de tags personnalisés"""

    file = File.query.first()

    if file:
        # Initialiser les tags
        file.set_metadata('tags', ['important', 'contract', '2024'])

        # Ajouter un tag
        tags = file.get_metadata('tags', [])
        tags.append('legal')
        file.set_metadata('tags', tags)

        # Catégorisation
        file.update_metadata({
            'category': 'legal',
            'subcategory': 'contracts',
            'department': 'sales',
            'project': 'Project Alpha'
        })

        db.session.commit()


def example_7_processing_status():
    """Exemple 7: Suivre l'état de traitement d'un fichier"""

    file = File.query.first()

    if file:
        # État initial
        file.update_metadata({
            'processing_status': 'pending',
            'processing_steps': {
                'uploaded': {'status': 'completed', 'timestamp': '2024-01-15T10:00:00Z'},
                'virus_scan': {'status': 'pending'},
                'ocr': {'status': 'pending'},
                'thumbnail': {'status': 'pending'}
            }
        })
        db.session.commit()

        # Mise à jour après scan
        steps = file.get_metadata('processing_steps')
        steps['virus_scan'] = {
            'status': 'completed',
            'timestamp': '2024-01-15T10:01:00Z',
            'result': 'clean'
        }
        file.set_metadata('processing_steps', steps)
        db.session.commit()


def example_8_search_by_metadata():
    """Exemple 8: Rechercher des fichiers par métadonnées (PostgreSQL JSONB)"""

    # Rechercher tous les fichiers JPEG
    jpeg_files = File.query.filter(
        File.metadata['mime_type'].astext == 'image/jpeg'
    ).all()

    print(f"Found {len(jpeg_files)} JPEG files")

    # Rechercher les images de plus de 1920px de large
    large_images = File.query.filter(
        File.metadata['width'].astext.cast(db.Integer) > 1920
    ).all()

    print(f"Found {len(large_images)} large images")

    # Rechercher les fichiers avec un tag spécifique
    important_files = File.query.filter(
        File.metadata['tags'].contains(['important'])
    ).all()

    print(f"Found {len(important_files)} important files")


def example_9_remove_metadata():
    """Exemple 9: Supprimer des métadonnées"""

    file = File.query.first()

    if file:
        # Supprimer une clé spécifique
        if file.remove_metadata('temp_flag'):
            print("Temporary flag removed")

        # Vérifier l'existence avant d'accéder
        if file.has_metadata('exif'):
            exif = file.get_metadata('exif')
            print(f"EXIF data available: {exif}")
        else:
            print("No EXIF data")

        db.session.commit()


def example_10_complete_workflow():
    """Exemple 10: Workflow complet d'upload et traitement"""

    # Simuler l'upload d'un fichier image
    file = File(
        md5_hash='a' * 32,
        s3_path='tenants/test/files/aa/aa/test.jpg',
        file_size=2048000,
        created_by='user-uuid'
    )

    # Métadonnées de base à l'upload
    file.update_metadata({
        'mime_type': 'image/jpeg',
        'original_filename': 'vacation-photo.jpg',
        'uploaded_from': 'web',
        'user_agent': 'Mozilla/5.0...'
    })

    db.session.add(file)
    db.session.flush()

    # Après traitement d'image
    file.update_metadata({
        'width': 4000,
        'height': 3000,
        'format': 'JPEG',
        'color_mode': 'RGB',
        'orientation': 'landscape',
        'has_exif': True,
        'exif': {
            'camera': 'iPhone 13 Pro',
            'date_taken': '2024-01-10T15:30:00Z',
            'gps_latitude': 48.8566,
            'gps_longitude': 2.3522
        }
    })

    # Après génération de miniature
    file.update_metadata({
        'thumbnails': {
            'small': {'width': 200, 'height': 150, 's3_path': 'thumbnails/small/...'},
            'medium': {'width': 800, 'height': 600, 's3_path': 'thumbnails/medium/...'},
            'large': {'width': 1600, 'height': 1200, 's3_path': 'thumbnails/large/...'}
        },
        'thumbnails_generated_at': '2024-01-10T15:31:00Z'
    })

    db.session.commit()

    print(f"File processed successfully: {file.id}")
    print(f"Metadata: {file.metadata}")


# Point d'entrée pour tester les exemples
if __name__ == '__main__':
    app = create_app()

    with app.app_context():
        print("=== Exemples d'utilisation de File.metadata ===\n")

        # Choisir les exemples à exécuter
        print("1. Métadonnées basiques")
        example_1_basic_metadata()

        print("\n2. Métadonnées d'image")
        example_2_image_metadata()

        print("\n3. Analyse de document")
        example_3_document_analysis()

        print("\n4. Scan antivirus")
        example_4_virus_scan()

        print("\n8. Recherche par métadonnées")
        example_8_search_by_metadata()
