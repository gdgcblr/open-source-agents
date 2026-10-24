def calculate_average(numbers):
    if not numbers:
        return 0

    total = sum(numbers)
    return total / len(numbers)


def main():
    scores = [80, 90, 70]
    average = calculate_average(scores)
    print(f"Average score: {average}")


if __name__ == "__main__":
    main()
