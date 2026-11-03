"""Optional local runner. GitHub Actions is the normal publisher."""
import argparse
import time

from scripts.update_values import run_cycle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--interval', type=int, default=3600, help='Seconds between local collection cycles')
    args = parser.parse_args()
    if args.interval < 60:
        parser.error('The interval must be at least 60 seconds')
    try:
        while True:
            started = time.monotonic()
            try:
                run_cycle()
            except Exception as error:
                print(f'Collection failed; retaining the last published snapshot: {error}')
            time.sleep(max(1, args.interval - (time.monotonic() - started)))
    except KeyboardInterrupt:
        print('Collector stopped.')


if __name__ == '__main__':
    main()
