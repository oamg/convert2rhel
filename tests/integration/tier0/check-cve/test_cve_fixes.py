from multiprocessing import Pool

import psutil


def watchdog():
    while True:
        for process in psutil.process_iter():
            # For some reason the psutil catches subscription-manager in process.name()
            # as 'subscription-ma', thus using 'subscription' to catch it
            if "subscription" in process.name():
                return process.cmdline()


def test_passing_password_to_submrg(convert2rhel):
    username = "testname"
    password = "&hTYGHKPvU7Ewd"
    with convert2rhel(f"-y --no-rpm-va -u {username} -p {password}") as c2r:
        # Just to be sure, try to run through all three tries
        # of the registration process in case the race condition applies
        for subscription_try in range(2):
            c2r.expect("Registering the system using subscription-manager ...")
            # Run watchdog function using multiprocessing pool
            # as soon as Convert2RHEL tries to call subscription-manager
            with Pool(processes=1) as pool:
                watcher = pool.apply_async(watchdog, ())
                # Check for the password not being passed to the subscription-manager
                print(watcher.get())
                assert not [cmdline for cmdline in watcher.get() if password in cmdline]
