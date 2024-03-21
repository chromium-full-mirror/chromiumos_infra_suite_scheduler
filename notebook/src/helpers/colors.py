import colored


def red(text: str) -> str:
    return f"{colored.Fore.red}{text}{colored.Style.reset}"


def blue(text: str) -> str:
    return f"{colored.Fore.blue}{text}{colored.Style.reset}"


def white(text: str) -> str:
    return f"{colored.Fore.white}{text}{colored.Style.reset}"
