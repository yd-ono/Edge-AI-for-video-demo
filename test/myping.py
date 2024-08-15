import pings

def myping(ipaddr):
    p = pings.Ping()
    res = p.ping(ipaddr)
    if res.is_reached():
        return True
    else:
        return False

if __name__ == '__main__':
    if myping("8.8.8.8"):
        print("OK")
    else:
        print("NG")