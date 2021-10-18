from tgtg import TgtgClient
from configparser import ConfigParser
import os

def main():
    script_dir = os.path.dirname(os.path.realpath(__file__)) 
    project_dir = os.path.dirname(script_dir)
    config_file = f'{project_dir}/config.ini'

    config = ConfigParser()
    config.read(config_file)

    print(config['tgtg']['email'])
    print(config['tgtg']['password'])
    client = TgtgClient(email=config['tgtg']['email'], password=config['tgtg']['password'])
    print(client.get_items())


if __name__ == "__main__":
    main()
