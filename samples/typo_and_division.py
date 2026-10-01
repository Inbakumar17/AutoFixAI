def average(values):
    total = sum(values)
    count = len(values)
    return total / count


def report(data):
    mean = averge(data)
    return "mean=" + str(mean)


print(report([2, 4, 6]))
print(average([]))
