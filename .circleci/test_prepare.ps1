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
$disturl = 'https://bintray.com/vszakats/generic/download_file?file_path=openssl-1.1.1g-win64-mingw.zip'
$disthash = '82ac63a9b0897a5707dd0cd5a67bb41d1e46066859fcfddfc0082a340ba08b6a'
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
$disturl = 'https://github.com/state-of-the-art/BlendNet/wiki/files/blendnet-test-project-2.82-v0.3.zip'
$wc.DownloadFile($disturl, "test-project-dist.zip")
echo "Unpack dist..."
Expand-Archive test-project-dist.zip
mv test-project-dist\* test-project
