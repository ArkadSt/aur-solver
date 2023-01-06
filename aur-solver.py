#!/usr/bin/env python3

import os
import subprocess
import re
import requests
import json
import argparse
import sys

ALL_STUFF: str = os.path.expanduser('~') + "/.aur-solver"
PWD: str = os.getcwd()

if not os.path.exists(ALL_STUFF):
    os.makedirs(ALL_STUFF)


def get_local_version(package: str) -> str:
    return subprocess.run('pacman -Qi ' + package + ' | awk \'/^Version/{printf "%s", $3}\'', shell=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode()


def get_packages_info(packages: list[str]) -> dict:
    url_string = "https://aur.archlinux.org/rpc/?v=5&type=info"
    for package in packages:
        url_string += f"&arg[]={package}"
    return json.loads(requests.get(url_string).text)


def get_remote_version(package: str) -> str:
    return get_packages_info([package])["results"][0]["Version"]


def install(packages_to_install: list[str], install_options: str) -> list[str]:
    package_info: dict = get_packages_info(packages_to_install)
    if package_info["resultcount"] != len(packages_to_install):
        sys.exit(
            f'Packages {[package for package in packages_to_install if get_packages_info([package])["resultcount"] == 0]} are not in the AUR')

    installed_aur_dependencies: list = []
    package_dir: str = ALL_STUFF + '/' + packages_to_install[0]

    if os.path.exists(package_dir):
        os.chdir(package_dir)
        print(f"Directory {os.getcwd()} exists, executing 'git pull'...")
        subprocess.run("git pull", shell=True)
        os.chdir(PWD)
    else:
        print("Cloning repository...")
        subprocess.run(f"git clone https://aur.archlinux.org/{packages_to_install[0]}.git {package_dir}", shell=True)

    try:
        for raw_dependency in package_info["results"][0]["Depends"] + package_info["results"][0]["MakeDepends"]:
            dependency = re.match(r'^([^><=]+)', raw_dependency).group()
            if subprocess.run(f"pacman -Si {dependency} > /dev/null 2>&1",
                              shell=True).returncode != 0 and get_packages_info([dependency])["resultcount"] == 1:
                if not (subprocess.run(f"pacman -Qi {dependency} > /dev/null 2>&1", shell=True).returncode == 0 and (
                        get_local_version(dependency) == get_remote_version(dependency))):
                    print(f"Installing dependency {dependency} from AUR...")
                    for dep in install([dependency], "--asdeps"):
                        try:
                            installed_aur_dependencies.append(dep)
                            packages_to_install.remove(dep)
                        except ValueError:
                            pass
    except KeyError:
        pass

    os.chdir(package_dir)

    pgp_keys: list[str] = subprocess.run("makepkg --printsrcinfo | awk '/validpgpkeys/{print $3}'", shell=True,
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode().split()
    for pgp in pgp_keys:
        if subprocess.run("gpg --list-keys | awk '/" + pgp + "/{print $1}'", shell=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE).stdout.decode() == "":
            print(f"Import PGP key {pgp}? (Y/n): ", end='')
            match input().lower():
                case "n":
                    print("Not importing key")
                case _:
                    print("Importing key...")
                    subprocess.run(f"gpg --recv-keys {pgp}", shell=True)

    subprocess.run(f"makepkg -si {install_options}", shell=True)
    os.chdir(PWD)

    if len(packages_to_install) > 1:
        return installed_aur_dependencies + [packages_to_install[0]] + install(
            [package for package in packages_to_install if package != packages_to_install[0]], install_options)
    else:
        return installed_aur_dependencies + [packages_to_install[0]]


def update():
    all_installed_aur_packages = subprocess.run("pacman -Qm | awk '{print $1}'", shell=True, stdout=subprocess.PIPE,
                                                stderr=subprocess.PIPE).stdout.decode().split()
    packages_info = get_packages_info(all_installed_aur_packages)

    flagged_out_of_date: list = []
    to_be_updated: list = []
    to_be_updated_output: str = ""

    for i in range(len(all_installed_aur_packages)):
        package = all_installed_aur_packages[i]
        remote_version = packages_info["results"][i]["Version"]
        if not (get_local_version(package) == remote_version):
            to_be_updated_output += f"{package} ({get_local_version(package)} => {remote_version})\n"
            to_be_updated.append(package)
        if packages_info["results"][i]["OutOfDate"] is not None:
            flagged_out_of_date.append(package)

    print(f"Flagged out-of-date: {', '.join(flagged_out_of_date) if flagged_out_of_date else 'None'}")
    print("To be updated: ")
    if to_be_updated:
        print(to_be_updated_output + "Do you want to proceed? (Y/n): ", end='')
        match input().lower():
            case "n":
                print("Abort")
            case _:
                print("Updating...")
                install(to_be_updated, "")
    else:
        print("None. Your AUR packages are up to date")


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

match args.action:
    case "install":
        if not len(args.packages) == 0:
            install(args.packages, "")
        else:
            parser.print_help()
    case "remove":
        if not len(args.packages) == 0:
            remove(args.packages)
        else:
            parser.print_help()
    case "update":
        update()
