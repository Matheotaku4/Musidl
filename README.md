# 🎵 CachyOS Music Downloader

Une belle application GUI pour télécharger de la musique depuis Tidal via l'API hifi-api.

## ✨ Fonctionnalités

- **Recherche musicale** : Recherchez des titres, albums ou artistes
- **Téléchargements multiples** : 
  - Télécharger un titre unique
  - Télécharger un album complet
  - Télécharger toute la discographie d'un artiste
- **Organisation automatique** : Les fichiers sont organisés comme suit :
  ```
  Dossier de téléchargement/
  └── Artiste/
      └── Artiste - Album/
          ├── 01 - Titre.flac
          ├── 01 - Titre.lrc (paroles synchronisées)
          ├── 02 - Autre titre.flac
          ├── 02 - Autre titre.lrc
          └── cover.jpg (pochette d'album)
  ```
- **Qualité audio** : Supporte plusieurs qualités dont le Hi-Res Lossless
- **Métadonnées** : Tags ID3/FLAC intégrés (titre, artiste, album, année, etc.)
- **Paroles** : Téléchargement automatique des fichiers .lrc si disponibles
- **Interface moderne** : Thème sombre inspiré de CachyOS

## 📋 Prérequis

### 1. Installer pipx (si ce n'est pas déjà fait)

Sur CachyOS/Arch Linux :
```bash
sudo pacman -S pipx
pipx ensurepath
# Redémarrez le terminal ou lancez : source ~/.bashrc
```

### 2. Installer et configurer hifi-api avec pipx

```bash
# Cloner hifi-api
git clone https://github.com/binimum/hifi-api.git
cd hifi-api

# Installer avec pipx
pipx install .

# Configurer l'authentification Tidal
cd tidal_auth
pipx runpip hifi-api install -r requirements.txt
python tidal_auth.py
# Suivez les instructions pour obtenir vos tokens

# Revenir au dossier principal et lancer l'API
cd ..
hifi-api  # Lance le serveur API
```

L'API sera disponible sur `http://localhost:8000` par défaut.

### 3. Installer les dépendances de l'application

**Option A (Recommandée sur CachyOS)** : Utiliser les paquets système
```bash
sudo pacman -S python-pyqt6 python-requests python-mutagen
```

**Option B** : Utiliser un environnement virtuel
```bash
cd /workspace
python -m venv venv
source venv/bin/activate
pip install PyQt6 requests mutagen
```

## 🚀 Utilisation

### Lancer l'application

**Avec les paquets système (Option A) :**
```bash
python cachyos_music_downloader.py
```

**Avec un environnement virtuel (Option B) :**
```bash
source venv/bin/activate
python cachyos_music_downloader.py
```

### Interface

1. **Configuration API** : Entrez l'URL de votre instance hifi-api (par défaut: `http://localhost:8000`)

2. **Recherche** :
   - Tapez votre recherche dans le champ de texte
   - Sélectionnez le type : Tracks, Albums, ou Artists
   - Cliquez sur "🔍 Search" ou appuyez sur Entrée

3. **Ajouter aux téléchargements** :
   - Double-cliquez sur un résultat pour l'ajouter à la file d'attente

4. **Paramètres de téléchargement** :
   - Choisissez le dossier de destination
   - Sélectionnez la qualité audio souhaitée

5. **Télécharger** :
   - Cliquez sur "⬇️ Start Download" pour commencer
   - "⏹️ Stop All" pour arrêter tous les téléchargements

## 🎨 Thème

L'application utilise un thème sombre moderne avec les couleurs de Tokyo Night :
- Fond : `#1a1b26`
- Accent : `#7aa2f7` (bleu)
- Texte : `#a9b1d6`
- Succès : `#9ece6a` (vert)

## ⚠️ Avertissement

Le téléchargement de musique protégée par des droits d'auteur peut être illégal dans votre pays. Cette application est fournie à des fins éducatives uniquement. Utilisez-la uniquement avec un compte Tidal valide et dans le respect des lois locales.

## 📁 Structure du projet

```
/workspace/
├── cachyos_music_downloader.py  # Application principale
├── README.md                     # Ce fichier
└── requirements.txt              # Dépendances Python
```

## 🔧 Personnalisation

Vous pouvez modifier les constantes suivantes dans le code :

- `DEFAULT_API_URL` : URL par défaut de l'API
- `DEFAULT_DOWNLOAD_DIR` : Dossier de téléchargement par défaut
- `QUALITY_OPTIONS` : Options de qualité disponibles

## 🐛 Dépannage

### L'API ne répond pas
- Vérifiez que hifi-api est bien lancé
- Assurez-vous que le port 8000 n'est pas utilisé par une autre application
- Vérifiez vos identifiants Tidal dans token.json

### Erreur de téléchargement
- Vérifiez votre connexion internet
- Assurez-vous que votre compte Tidal est actif
- Essayez une qualité audio inférieure

### Problème d'interface graphique
- Sous Linux/CachyOS, installez les paquets Qt nécessaires : `sudo pacman -S python-pyqt6`
- Vérifiez que PyQt6 est correctement installé
- Si vous utilisez pipx, assurez-vous que le chemin est bien configuré : `pipx ensurepath`

## 📝 Licence

Ce projet est fourni tel quel. Veuillez respecter les conditions d'utilisation de Tidal et les lois sur le droit d'auteur applicables dans votre pays.