#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>

MODULE_LICENSE("Proprietary");
//MODULE_LICENSE("GPL");
MODULE_AUTHOR("Martin Litwora");
MODULE_DESCRIPTION("Module for testing purpose, prints 'Hello world!'");

static int __init hello_init(void)
{
    printk(KERN_INFO "Hello world!\n");
    return 0;
}

static void __exit hello_cleanup(void)
{
    printk(KERN_INFO "Cleaning up module.\n");
}

module_init(hello_init);
module_exit(hello_cleanup);
