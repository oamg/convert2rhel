obj-m += my_kmod.o

all:
	make -C /lib/modules/$(shell uname -r)/build M=/tmp/my-test/ modules
