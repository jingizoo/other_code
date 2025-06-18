# from the repo root (the same place you built)
docker run --rm \
  -v "$(pwd)":/app \               # mount your source tree read-write
  -w /app/pte/accounting/external-services/acctgateway/data-mesh/peoplesoft_data_archive_partitions \
  ps-partitions:latest \
  python clean_fy.py --fy 2015 --dry-run
