# Official PyPA manylinux2014: CentOS 7 / glibc 2.17, x86_64.
FROM quay.io/pypa/manylinux2014_x86_64@sha256:21c37461985655aaa25ed3a923b28e6c9d4dd9e10edc0281eb50385184bddd31

# manylinux's CPython is static. Build its matching shared embedding library;
# keep the image's existing stdlib/extensions (including SSL and SQLite).
# Source checksum: https://www.python.org/downloads/release/python-31214/
RUN cd /tmp && \
    curl -fsSLO https://www.python.org/ftp/python/3.12.14/Python-3.12.14.tar.xz && \
    echo '5c8462af5790baf43a321a1559dbe0db06d1be4300fb85fb53c40060668e548a  Python-3.12.14.tar.xz' | sha256sum -c - && \
    tar -xf Python-3.12.14.tar.xz && \
    cd Python-3.12.14 && \
    ./configure --enable-shared --without-ensurepip && \
    make -j2 libpython3.12.so && \
    cp libpython3.12.so.1.0 /opt/python/cp312-cp312/lib/ && \
    cd /tmp && rm -rf Python-3.12.14 Python-3.12.14.tar.xz

ENV PATH="/opt/python/cp312-cp312/bin:${PATH}"
RUN python -m pip install --no-cache-dir uv==0.12.10
WORKDIR /src
CMD ["sh", "packaging/build-linux.sh"]
