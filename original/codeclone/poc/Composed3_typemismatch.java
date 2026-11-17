import java.util.Arrays;

// A2;C -- idx=1668091 (sort) then idx=14632238 (bubble, from cluster 2450, NOT the
// hash cluster 13771944 that B1/B2 came from). C substitutes for B2.
// Expect: output diverges from Composed1/Composed2 -- confirms the label flips
// to non-equivalent when a member of a non-equivalent class is substituted in.
public class Composed3 {

    // idx=1668091
    protected static int[] sort(int[] arr) {
        for (int i = arr.length - 1; i > 0; i--) {
            for (int j = 0; j < i; j++) {
                if (arr[j] > arr[j + 1]) {
                    int temp = arr[j];
                    arr[j] = arr[j + 1];
                    arr[j + 1] = temp;
                }
            }
        }
        return arr;
    }

    // idx=14632238 (C: different cluster than B)
    public static void bubble(double[] a) {
        for (int i = a.length - 1; i > 0; i--) for (int j = 0; j < i; j++) if (a[j] > a[j + 1]) {
            double temp = a[j];
            a[j] = a[j + 1];
            a[j + 1] = temp;
        }
    }

    public static void main(String[] args) throws Exception {
        int[] arr = {5, 3, 8, 1, 9, 2};
        int[] sorted = sort(arr);
        double[] darr = {5.5, 3.3, 8.8, 1.1, 9.9, 2.2};
        bubble(darr);
        System.out.println(Arrays.toString(sorted));
        System.out.println(Arrays.toString(darr));
    }
}
