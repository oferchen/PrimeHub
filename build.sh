#!/bin/bash
set -e

# Read version from addon.xml
VERSION=$(grep '<addon ' plugin.video.primeflix/addon.xml | grep -o 'version="[^"]*"' | sed 's/version="\([^"]*\)"/\1/')
if [ -z "$VERSION" ]; then
    echo "Could not find version in addon.xml"
    exit 1
fi

ZIP_NAME="plugin.video.primeflix-${VERSION}.zip"
echo "Packaging add-on version ${VERSION} into ${ZIP_NAME}"

# Remove old zip if it exists
rm -f "${ZIP_NAME}"

VENDOR_DIR="plugin.video.primeflix/resources/lib/vendor"

echo "Bundling Python dependencies..."
# Create vendor directory
mkdir -p "${VENDOR_DIR}"
# Install dependencies from requirements.txt into the vendor directory
pip install -r requirements.txt --target="${VENDOR_DIR}"

# Create the new zip file, excluding common unnecessary files
echo "Creating zip file..."
zip -r "${ZIP_NAME}" plugin.video.primeflix -x "*.DS_Store" "*/.DS_Store" "*__pycache__*" "*.pyc"

# Clean up vendor directory
echo "Cleaning up..."
rm -rf "${VENDOR_DIR}"

echo "Successfully created ${ZIP_NAME}"
