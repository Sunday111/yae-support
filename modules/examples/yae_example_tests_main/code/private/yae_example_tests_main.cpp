#include "gtest/gtest.h"
#include "yae_example_header_only/yae_example_header_only.hpp"
#include "yae_example_library/yae_example_library.hpp"

TEST(YaeExampleTest, HeaderOnlyLibrary)
{
    yae::example_header_only::Test object;
    ASSERT_EQ(object.GetValue(), 42);
}

TEST(YaeExampleTest, OnlyLibrary)
{
    yae::example_library::Test object;
    ASSERT_EQ(object.GetValue(), 24);
}
