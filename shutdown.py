import docker
from time import sleep
from get_logs import get_logs_for_container

def shutdown():
    print("+" + "-"*78 + "+")
    print("| %-76s |" % "Grabbing logs, stopping, and removing all docker containers...")
    print("| %-76s |" % "Please wait, as this may take a while.")
    print("+" + "-"*78 + "+")
    client = docker.from_env()
    cont_list = client.containers.list(True) 
    for i, cont in enumerate(cont_list):
        try:
            print("(%d/%d) Resolving %s...." % (i+1, len(cont_list), cont.name))
            get_logs_for_container(cont)
            cont.stop()
            cont.remove()
        except KeyboardInterrupt:
            print("Are you sure you want to stop this? If so, hit Ctrl-C again.")
            sleep(5)
        except Exception as e:
            print("Faild to shut down the container: %s aka %s!" % (cont.id, cont.name))
            print("Reasion:")
            print(e)
            print("Continuing...")
    print("+" + "-"*78 + "+")
    print("| %-76s |" % "All done! Have a nice day! :)")
    print("+" + "-"*78 + "+")

if __name__ == '__main__':
    shutdown()
