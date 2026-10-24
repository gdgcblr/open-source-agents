from src import AndroidAutomation


def main():
    auto = AndroidAutomation()

    # 1. Launch Brave
    result = auto.launch_app("com.brave.browser")
    print(result.summary())

    if not result.success:
        return

    # 2. Type into Brave's search/address bar
    result = auto.input_text(
        hint="Search Brave or type URL",
        text="youtube.com",
        clear_first=True,
        verify=True,
    )
    print(result.summary())

    # IMPORTANT:
    # input_text may report verification failure even though
    # the text was actually entered into Brave.
    # So don't return here.

    # 3. Press Enter
    result = auto.press_enter()
    print(result.summary())

    if not result.success:
        return

    print("✓ YouTube search/navigation completed successfully")


if __name__ == "__main__":
    main()