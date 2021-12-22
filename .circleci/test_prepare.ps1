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
$disturl = 'https://curl.se/windows/dl-7.80.0_2/openssl-3.0.1_2-win64-mingw.zip'
$disthash = 'd19096170fc47ac0284077b9a925b83cd6f4ed0268fbb54cd6de171cd0735c1d'
$wc.DownloadFile($disturl, "openssl-dist.zip")
$FileHash = Get-FileHash openssl-dist.zip -Algorithm SHA256
$FileHash.Hash -eq $disthash
echo "Unpack dist..."
Expand-Archive openssl-dist.zip
mv openssl-dist\* openssl

echo "Create the template workspace & prepare certificates"
mkdir workspace
openssl\bin\openssl.exe req -x509 -nodes -newkey rsa:4096 `
    -keyout workspace\server.key -out workspace\server.crt `
    -days 365 -subj "/C=US/ST=N/L=N/O=N/OU=N/CN=blendet-service" `
    -config .\openssl\ssl\openssl.cnf
# Required ca.crt for Manager
cp workspace\server.crt workspace\ca.crt

echo "Download the test project"
$disturl = 'https://github.com/state-of-the-art/BlendNet-test-project/archive/v2.82-v0.4.zip'
$wc.DownloadFile($disturl, "test-project-dist.zip")
echo "Unpack dist..."
Expand-Archive test-project-dist.zip
mv test-project-dist\* test-project
