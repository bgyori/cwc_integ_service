Setup steps
-----------
1. Run `aws_util.py` to launch an EC2 instance
2. SSH into the instance and transfer/manually paste and run commands in
`instance_setup.sh` which is _not_ yet fully automated so it's better done
with human supervision
3. Run `guni.sh` on the instance to start the service
4. Test by going to [instance public IP]:8080 in a browser
