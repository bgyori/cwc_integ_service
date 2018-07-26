# This script contains commans to run on the instance after creation
sudo apt-get update
sudo apt-get install -y python-setuptools python-dev build-essential python3-pip
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"
sudo apt-get update
sudo apt-get install -y docker-ce
sudo usermod -aG docker ${USER}
#NOTE: one actually has to log out and in again for this to take effect
git clone https://github.com/bgyori/cwc_integ_service.git
cd cwc_integ_service/
pip3 install -r requirements.txt
sudo apt-get install -y gunicorn
sudo apt-get install -y mongodb
sudo /etc/init.d/mongodb start
sudo mkdir /pmc
#TODO: this path "xvdy" actually changes each time. One has to run lsblk
# to find the 1000G device and look at its device name and replace that for
# xvdy here
sudo mount /dev/xvdy /pmc/
#TODO: open up /etc/docker/daemon.json for editing and add the block below.
# This could be done automatically
# {
#    "graph": "/pmc/docker",
#    "storage-driver": "overlay"
#}
sudo systemctl daemon-reload
sudo systemctl restart docker
sudo apt-get install nginx
# Add
# server {
#    listen 80;
#    server_name <server's public IP>;
#
#     location / {
#         proxy_pass http://<server's public IP>:8080;
#         }
#}
# to /etc/nginx/sites-available/cwc_integ_service
# obviously depending on the actual IP of the server
sudo ln -s /etc/nginx/sites-available/cwc_integ_service /etc/nginx/sites-enabled
sudo rm /etc/nginx/sites-enabled/default
sudo systemctl restart nginx
