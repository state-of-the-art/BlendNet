# PowerShell script to prepare the windows env

echo "Prepare the environment to execute tests"
$global:ProgressPreference = "SilentlyContinue" # For Expand-Archive
$wc = [System.Net.WebClient]::new()

echo "Download the blender dist"
$disturl = 'https://download.blender.org/release/Blender2.90/blender-2.90.0-windows64.zip'
$disthash = 'f51e1c33f6c61bdef86008280173e4c5cf9c52e4f5c490e9a7e4db3a355639bc'
$wc.DownloadFile($disturl, "blender-dist.zip")
$FileHash = Get-FileHash blender-dist.zip -Algorithm SHA256
$FileHash.Hash -eq $disthash
echo "Unpack dist..."
Expand-Archive blender-dist.zip
mv blender-dist\* blender

echo "Download the openssl dist"
$disturl = 'https://curl.se/windows/dl-7.75.0_4/openssl-1.1.1j_4-win64-mingw.zip'
$disthash = 'a4a17651456324b79f2a00b0f978edfa1d93a282bbdf197492c394e89a3f9b25'
$wc.DownloadFile($disturl, "openssl-dist.zip")
$FileHash = Get-FileHash openssl-dist.zip -Algorithm SHA256
$FileHash.Hash -eq $disthash
echo "Unpack dist..."
Expand-Archive openssl-dist.zip
mv openssl-dist\* openssl

echo "Create the template workspace & prepare certificates"
mkdir workspace
openssl\openssl.exe req -x509 -nodes -newkey rsa:4096 `
    -keyout workspace\server.key -out workspace\server.crt `
    -days 365 -subj "/C=US/ST=N/L=N/O=N/OU=N/CN=blendet-service" `
    -config .\openssl\openssl.cnf
# Required ca.crt for Manager
cp workspace\server.crt workspace\ca.crt

echo "Download the test project"
$disturl = 'https://github.com/state-of-the-art/BlendNet-test-project/archive/v2.82-v0.4.zip'
$wc.DownloadFile($disturl, "test-project-dist.zip")
echo "Unpack dist..."
Expand-Archive test-project-dist.zip
mv test-project-dist\* test-project
