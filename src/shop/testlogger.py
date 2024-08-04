from shop.logger import logger
import time


def main():
    logger.info(f"info message {time.time()}")


if __name__ == "__main__":
    main()
