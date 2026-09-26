FROM ubuntu:22.04

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive
ENV TERM=xterm-256color

# Install core troubleshooting and DevOps tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    coreutils \
    util-linux \
    findutils \
    procps \
    htop \
    sysstat \
    stress-ng \
    lsof \
    strace \
    iproute2 \
    net-tools \
    iputils-ping \
    dnsutils \
    curl \
    wget \
    netcat-openbsd \
    tcpdump \
    iptables \
    tree \
    jq \
    vim \
    nano \
    less \
    grep \
    sed \
    gawk \
    file \
    tar \
    gzip \
    bzip2 \
    sudo \
    python3 \
    python3-pip \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create devops user (with sudo) and appuser
RUN useradd -m -s /bin/bash -u 1000 devops && \
    echo "devops ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/devops && \
    chmod 0440 /etc/sudoers.d/devops && \
    useradd -m -s /bin/bash -u 1001 appuser

# Set up standard directories
RUN mkdir -p /opt/services /opt/scripts /var/log/app /etc/app /run/services && \
    chown -R devops:devops /opt/services /var/log/app /etc/app /run/services

# Copy scripts and services into container
COPY lab/scripts/systemctl /usr/local/bin/systemctl
COPY lab/scripts/journalctl /usr/local/bin/journalctl
COPY lab/scripts/clean_state.sh /opt/scripts/clean_state.sh
COPY lab/services/web_app.py /opt/services/web_app.py
COPY lab/services/payment_api.py /opt/services/payment_api.py
COPY lab/entrypoint.sh /entrypoint.sh

RUN chmod +x /usr/local/bin/systemctl /usr/local/bin/journalctl /opt/scripts/clean_state.sh /entrypoint.sh

# Workdir & user
WORKDIR /home/devops
USER devops

ENTRYPOINT ["/bin/bash", "/entrypoint.sh"]
