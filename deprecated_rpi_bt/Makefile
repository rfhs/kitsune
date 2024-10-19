DESTDIR := /

install:
	install -d $(DESTDIR)/opt/rfctf/
	install -m 755 kitsune $(DESTDIR)/opt/rfctf/
	install -m 644 kitsune.conf $(DESTDIR)/opt/rfctf/
	install -m 644 kitsune.service $(DESTDIR)/etc/systemd/system/
	[ -x "/usr/bin/bc" ] || apt-get install bc -y
	systemctl daemon-reload
