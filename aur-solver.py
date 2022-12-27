#!/usr/bin/env python3

import os
import subprocess
import re
import requests
import json
import argparse
import sys

ALL_STUFF = os.path.expanduser('~') + "/.aur-solver"
PWD = os.getcwd()

if not os.path.exists(ALL_STUFF):
    os.makedirs(ALL_STUFF)


def get_local_version(package: str) -> str:
    return subprocess.run('pacman -Qi ' + package + ' | awk \'/^Version/{printf "%s", $3}\'', shell=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode()


def get_packages_info(packages: list) -> dict:
    url_string = "https://aur.archlinux.org/rpc/?v=5&type=info"
    for package in packages:
        url_string += f"&arg[]={package}"
    return json.loads(requests.get(url_string).text)


def get_remote_version(package: str) -> str:
    return get_packages_info([package])["results"][0]["Version"]


def install(packages_to_install: list, install_options: str) -> list:
    package_info = get_packages_info(packages_to_install)
    if package_info["resultcount"] != len(packages_to_install):
        for package in packages_to_install:
            if get_packages_info([package])["resultcount"] == 0:
                print(f"{package} is not in the AUR")
        sys.exit()

    installed_aur_dependencies = []
    package_dir = ALL_STUFF + '/' + packages_to_install[0]

    if os.path.exists(package_dir):
        os.chdir(package_dir)
        subprocess.run("git pull", shell=True)
        os.chdir(PWD)
    else:
        subprocess.run(f"git clone https://aur.archlinux.org/{packages_to_install[0]}.git {package_dir}", shell=True)

    for raw_dependency in package_info["results"][0]["Depends"]:
        dependency = re.match(r'^([^><=]+)', raw_dependency).group()
        if not subprocess.run(f"pacman -Si {dependency} > /dev/null 2>&1", shell=True).returncode == 0:
            if not (subprocess.run(f"pacman -Qi {dependency} > /dev/null 2>&1", shell=True).returncode == 0 and (
                    get_local_version(dependency) == get_remote_version(dependency))):
                print(f"Installing dependency {dependency}")
                for dep in install([dependency], "--asdeps"):
                    try:
                        print(f"removed {dep} from the queue of {packages_to_install}")
                        installed_aur_dependencies.append(dep)
                        packages_to_install.remove(dep)
                    except ValueError:
                        pass

    os.chdir(package_dir)
    subprocess.run("makepkg -s 2>/dev/null", shell=True)
    subprocess.run(f"sudo pacman -U {install_options} {packages_to_install[0]}*.pkg.tar.zst", shell=True)
    os.chdir(PWD)

    if len(packages_to_install) > 1:
        packages_to_install.remove(packages_to_install[0])
        return installed_aur_dependencies + [packages_to_install[0]] + install(packages_to_install, install_options)
    else:
        return installed_aur_dependencies + [packages_to_install[0]]


def update():
    all_installed_aur_packages = subprocess.run("pacman -Qm | awk '{print $1}'", shell=True, stdout=subprocess.PIPE,
                                                stderr=subprocess.PIPE).stdout.decode().split()
    packages_info = get_packages_info(all_installed_aur_packages)

    to_be_updated = []
    print("To be updated: ")
    for i in range(len(all_installed_aur_packages)):
        package = all_installed_aur_packages[i]
        remote_version = packages_info["results"][i]["Version"]
        if not (get_local_version(package) == remote_version):
            print(f"{package} ({get_local_version(package)} => {remote_version})")
            to_be_updated.append(package)

    if not to_be_updated:
        print("None. Your AUR packages are up to date")
        return

    print("Do you want to proceed? (Y/n): ", end='')
    match input():
        case "n":
            print("Abort")
        case _:
            install(to_be_updated, "")


def remove(packages: list):
    line = ""
    for package in packages:
        line += package + " "
    subprocess.run(f"sudo pacman -Rs {line}", shell=True)


parser = argparse.ArgumentParser()
parser.add_argument('action', choices=['install', 'update', 'remove'],
                    help="'update' doesn't take arguments, others do.")
parser.add_argument('packages', nargs='*', help='Package name(s)')
args = parser.parse_args()

try:
    match args.action:
        case "install":
            install(args.packages, "")
        case "remove":
            remove(args.packages)
        case "update":
            update()
except IndexError:
    parser.print_help()
